# AI editing guide

Scope: only the `copy-except-tar` tool in this repository.

- Keep the repository independently runnable; do not reference sibling repositories.
- Put generated data in `cache/`, `state/`, or `venvs/`; these paths are Git-ignored.
- Keep `run.sh` as the stable user-facing entry point.
- This tool copies a source directory to a destination, excluding specified subfolder paths using rsync. Preserve the confirmation prompt, path validation, and dry-run behavior — do not weaken these guards.
- Preserve workstation-specific defaults unless the user explicitly asks to generalize them.
- Validate shell with `bash -n` and Python with `python3 -m py_compile` before finishing.
