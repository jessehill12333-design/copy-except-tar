#!/usr/bin/env bash

terminal_pause_allowed_for_args() {
    [[ "${CI:-}" != 1 ]] || return 1
    [[ "${TUMBLE_TERMINAL_NO_PAUSE:-0}" != 1 ]] || return 1
    local arg
    for arg in "$@"; do
        [[ "$arg" == --yes || "$arg" == -y ]] && return 1
    done
    return 0
}

terminal_pause_requested() {
    terminal_pause_allowed_for_args "$@" || return 1
    # A desktop terminal can expose /dev/tty while stdin is a pipe. Require
    # terminal stdout and reject piped stdin so CI and pipelines stay safe.
    [[ -t 1 && ! -p /dev/stdin && -r /dev/tty ]]
}

terminal_status_pause_on_exit() {
    local status=$?
    trap - EXIT
    if [[ "${TERMINAL_STATUS_PAUSE_DONE:-0}" != 1 ]] &&
        [[ "${TERMINAL_STATUS_PAUSE_ACTIVE:-0}" == 1 ]] &&
        { exec 3<>/dev/tty; } 2>/dev/null; then
        echo
        if (( status == 0 )); then
            printf 'SUCCESS: %s finished.\n' "${TERMINAL_STATUS_TITLE:-script}"
        else
            printf 'FAILED: %s did not complete successfully.\n' "${TERMINAL_STATUS_TITLE:-script}"
        fi
        printf 'Press any key to exit.'
        read -r -n 1 -s <&3 || true
        exec 3>&-
        echo
    fi
    exit "$status"
}

terminal_install_status_pause() {
    if terminal_pause_requested "$@"; then
        TERMINAL_STATUS_PAUSE_ACTIVE=1
        trap terminal_status_pause_on_exit EXIT
    fi
}

relaunch_in_terminal_if_needed() {
    local title
    title="${TERMINAL_STATUS_TITLE:-$(basename -- "$0" .sh)}"

    if [[ -t 0 || -t 1 ]]; then
        if [[ "${TUMBLE_TERMINAL_RELAUNCHED:-0}" != 1 ]] &&
            [[ "${TERMINAL_SELF_PAUSE:-0}" != 1 ]] &&
            terminal_pause_requested "$@"; then
            TERMINAL_STATUS_TITLE="$title"
            terminal_install_status_pause "$@"
        fi
        return 0
    fi

    # Skip in headless contexts (cron, ssh without X forwarding). Plasma sets
    # INVOCATION_ID and DISPLAY on menu launches just like systemd timers do,
    # so those can't be told apart here — scripts meant to run from timers
    # (the backup checker/weekly scripts) must not call this function.
    [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && return 0
    terminal_pause_allowed_for_args "$@" || return 0
    [[ ! -p /dev/stdin ]] || return 0
    local quoted=()
    local script_q q cmd success_q failure_q display_title
    printf -v script_q '%q' "$0"
    title="${TERMINAL_STATUS_TITLE:-$(basename -- "$0" .sh)}"
    display_title="${TERMINAL_STATUS_TITLE:-$title}"
    printf -v success_q '%q' "SUCCESS: $display_title finished."
    printf -v failure_q '%q' "FAILED: $display_title did not complete successfully."
    for arg in "$@"; do
        printf -v q '%q' "$arg"
        quoted+=("$q")
    done
    if [[ "${TERMINAL_SELF_PAUSE:-0}" == 1 ]] || ! terminal_pause_allowed_for_args "$@"; then
        # The calling script owns the completion pause. Adding another read
        # here leaves desktop launches waiting for two key presses.
        cmd="printf '\\033]0;%s\\007' '$title'; TUMBLE_TERMINAL_RELAUNCHED=1 $script_q ${quoted[*]}"
    else
        cmd="printf '\\033]0;%s\\007' '$title'; TUMBLE_TERMINAL_RELAUNCHED=1 $script_q ${quoted[*]}; status=\$?; echo; if [[ \$status -eq 0 ]]; then printf '%s\\n' $success_q; else printf '%s\\n' $failure_q; fi; printf 'Press any key to exit.'; read -n 1 -s -r || true; echo; exit \$status"
    fi
    if command -v konsole >/dev/null 2>&1; then
        exec konsole --new-tab -e bash -lc "$cmd"
    fi
    for term in gnome-terminal mate-terminal xfce4-terminal; do
        if command -v "$term" >/dev/null 2>&1; then
            exec "$term" --tab -- bash -lc "$cmd"
        fi
    done
    if command -v x-terminal-emulator >/dev/null 2>&1; then
        exec x-terminal-emulator -e bash -lc "$cmd"
    fi
}
