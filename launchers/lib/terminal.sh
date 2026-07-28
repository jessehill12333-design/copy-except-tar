#!/usr/bin/env bash

relaunch_in_terminal_if_needed() {
    [[ -t 0 ]] && return 0
    # Skip in headless contexts (cron, ssh without X forwarding). Plasma sets
    # INVOCATION_ID and DISPLAY on menu launches just like systemd timers do,
    # so those can't be told apart here — scripts meant to run from timers
    # (the backup checker/weekly scripts) must not call this function.
    [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && return 0
    local quoted=()
    local script_q q cmd title
    printf -v script_q '%q' "$0"
    title="$(basename -- "$0" .sh)"
    for arg in "$@"; do
        printf -v q '%q' "$arg"
        quoted+=("$q")
    done
    if [[ "${TERMINAL_SELF_PAUSE:-0}" == 1 ]]; then
        # The calling script owns the completion pause. Adding another read
        # here leaves desktop launches waiting for two key presses.
        cmd="printf '\\033]0;%s\\007' '$title'; $script_q ${quoted[*]}"
    else
        cmd="printf '\\033]0;%s\\007' '$title'; $script_q ${quoted[*]}; status=\$?; echo; read -n 1 -s -r -p '--- finished. Press any key to close. ---'; exit \$status"
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
