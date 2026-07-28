#!/usr/bin/env python3
"""Copy a source directory to a destination, excluding specified subfolder paths."""

from __future__ import annotations

import argparse
import os
import select
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy a source directory to a destination, excluding specified subfolder paths.")
    parser.add_argument("source", nargs="?", help="Source directory to copy (prompts when omitted)")
    parser.add_argument("dest", nargs="?", help="Destination directory (prompts when omitted)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be copied without copying")
    return parser.parse_args()


def resolve_path(raw: str) -> Path | None:
    raw = raw.strip().strip("\"'")
    if not raw:
        return None
    p = Path(raw).expanduser().resolve()
    return p


def validate_source(p: Path) -> str | None:
    if not p.exists():
        return f"Path does not exist: {p}"
    if not p.is_dir():
        return f"Not a directory: {p}"
    return None


def validate_dest(p: Path) -> str | None:
    if p.exists() and not p.is_dir():
        return f"Destination exists and is not a directory: {p}"
    return None


def compute_total_bytes(source: Path, excludes: list[str]) -> int:
    total = 0
    source_str = str(source)
    for dirpath, dirnames, filenames in os.walk(source):
        rel = os.path.relpath(dirpath, source_str)
        if rel == ".":
            rel = ""
        i = len(dirnames) - 1
        while i >= 0:
            d_rel = os.path.join(rel, dirnames[i]) if rel else dirnames[i]
            for ex in excludes:
                if d_rel == ex or d_rel.startswith(ex + "/") or d_rel.startswith(ex + os.sep):
                    del dirnames[i]
                    break
            i -= 1
        for f in filenames:
            f_rel = os.path.join(rel, f) if rel else f
            skip = False
            for ex in excludes:
                if f_rel == ex or f_rel.startswith(ex + "/") or f_rel.startswith(ex + os.sep):
                    skip = True
                    break
            if not skip:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
    return total


def format_bytes(n: int) -> str:
    for unit in ("", "K", "M", "G", "T"):
        if abs(n) < 1024:
            return f"{n:,.0f}{unit}" if unit == "" else f"{n:.1f}{unit}" if unit == "K" else f"{n:.2f}{unit}"
        n /= 1024
    return f"{n:.2f}P"


def build_tar_read_cmd(source: Path, excludes: list[str], verbose: bool = False) -> list[str]:
    cmd = ["tar", "cf", "-"]
    if verbose:
        cmd.append("-v")
    for ex in excludes:
        cmd.extend(["--exclude", ex])
    cmd.extend(["-C", str(source), "."])
    return cmd


def build_tar_list_cmd(source: Path, excludes: list[str]) -> list[str]:
    cmd = ["tar", "tf", "-"]
    for ex in excludes:
        cmd.extend(["--exclude", ex])
    cmd.extend(["-C", str(source), "."])
    return cmd


def confirm_yes(question: str) -> bool:
    try:
        answer = input(f"{question} [Y/n] ").strip().lower()
    except EOFError:
        return False
    return answer in ("", "y", "yes")


def print_banner() -> None:
    print("=" * 70)
    print("  copy-except-tar — copy a directory excluding specified subfolders")
    print("  Uses tar pipe for fast sequential transfer.")
    print("  Source files are COPIED (not moved). Nothing is deleted.")
    print()
    print("  Enter blank at any prompt to skip to the next step.")
    print("  Confirm the summary to proceed with the actual copy.")
    print("=" * 70)


def prompt_source() -> Path | None:
    while True:
        try:
            raw = input("\nSource directory to copy: ").strip().strip("\"'")
        except EOFError:
            return None
        if not raw:
            print("No source provided. Exiting.")
            return None
        p = resolve_path(raw)
        err = validate_source(p)
        if err:
            print(f"  ERROR: {err}")
            continue
        return p


def prompt_dest() -> Path | None:
    while True:
        try:
            raw = input("\nDestination directory: ").strip().strip("\"'")
        except EOFError:
            return None
        if not raw:
            print("No destination provided. Exiting.")
            return None
        p = resolve_path(raw)
        err = validate_dest(p)
        if err:
            print(f"  ERROR: {err}")
            continue
        return p


def normalize_exclude(raw: str, source: Path) -> str:
    excluded = Path(raw.strip().strip("\"'"))
    if excluded.is_absolute():
        try:
            resolved = excluded.resolve()
            rel = resolved.relative_to(source)
            return str(rel)
        except (ValueError, RuntimeError):
            pass
        rel = excluded.relative_to(excluded.anchor)
        return str(rel)
    return raw.strip().strip("\"'")


def prompt_excludes(source: Path) -> list[str]:
    excludes = []
    print("\nExcluded subfolder paths (relative or absolute).")
    print("Absolute paths under the source are auto-converted to relative.")
    print("Enter one per line. Leave blank to finish adding exclusions.")
    while True:
        try:
            raw = input("  Exclude (blank to finish): ").strip()
        except EOFError:
            break
        if not raw:
            break
        normalized = normalize_exclude(raw, source)
        excludes.append(normalized)
    return excludes


def show_summary(source: Path, dest: Path, excludes: list[str], dry_run: bool) -> None:
    print()
    print("=" * 70)
    print("  COPY SUMMARY")
    print("=" * 70)
    print(f"  Source:      {source}")
    print(f"  Destination: {dest}")
    if excludes:
        print("  Exclusions:")
        for ex in excludes:
            print(f"    - {ex}")
    else:
        print("  Exclusions:  (none)")
    print(f"  Mode:        {'DRY RUN (no files changed)' if dry_run else 'LIVE COPY'}")
    print("=" * 70)


def main() -> int:
    args = parse_args()
    print_banner()

    if args.source and args.dest:
        source = resolve_path(args.source)
        dest = resolve_path(args.dest)
        if source is None or dest is None:
            print("Invalid source or destination path.", file=sys.stderr)
            return 2
        src_err = validate_source(source)
        if src_err:
            print(f"ERROR: {src_err}", file=sys.stderr)
            return 1
        dst_err = validate_dest(dest)
        if dst_err:
            print(f"ERROR: {dst_err}", file=sys.stderr)
            return 1
        excludes = prompt_excludes(source)
    else:
        source = prompt_source()
        if source is None:
            return 2
        dest = prompt_dest()
        if dest is None:
            return 2
        excludes = prompt_excludes(source)

    dry_run = args.dry_run
    dest = dest / source.name
    show_summary(source, dest, excludes, dry_run)

    if not dry_run:
        if not confirm_yes("\nProceed with copy?"):
            print("Cancelled.")
            return 0

    dest.mkdir(parents=True, exist_ok=True)

    if dry_run:
        cmd = build_tar_list_cmd(source, excludes)
        print(f"\nDry run: file list from {' '.join(cmd)}")
        print()
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(f"\ntar finished with exit code {result.returncode}", file=sys.stderr)
            return result.returncode
        print("\nDry run complete. No files were changed.")
        return 0

    total_bytes = compute_total_bytes(source, excludes)
    total_str = format_bytes(total_bytes)
    start_time = time.time()
    paused_time = 0.0
    pause_start = 0.0
    paused = False
    pause_done = threading.Event()
    print(f"{'Bytes':>12} {'Total':>12} {'Speed':>12} {'Avg':>12} {'Elapsed':>9}", file=sys.stderr)

    tar_read_cmd = build_tar_read_cmd(source, excludes, verbose=True)
    tar_read = subprocess.Popen(tar_read_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    tar_write = subprocess.Popen(
        ["tar", "xf", "-", "-C", str(dest)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE
    )

    current_file = ""

    def pause_listener() -> None:
        nonlocal paused, paused_time, pause_start
        if not sys.stdin.isatty():
            return
        while not pause_done.is_set():
            r, _, _ = select.select([sys.stdin], [], [], 0.3)
            if r:
                ch = sys.stdin.read(1)
                if ch in ('p', 'P'):
                    if paused:
                        os.kill(tar_read.pid, signal.SIGCONT)
                        os.kill(tar_write.pid, signal.SIGCONT)
                        paused_time += time.time() - pause_start
                        paused = False
                    else:
                        pause_start = time.time()
                        os.kill(tar_read.pid, signal.SIGSTOP)
                        os.kill(tar_write.pid, signal.SIGSTOP)
                        paused = True

    def read_tar_stderr() -> None:
        nonlocal current_file
        for raw_line in iter(tar_read.stderr.readline, b''):
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            if line.strip():
                raw = line.lstrip("./")
                current_file = raw.rsplit("/", 1)[-1] if "/" in raw else raw

    def read_write_stderr(proc, label: str) -> None:
        for raw_line in iter(proc.stderr.readline, b''):
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            if line.strip():
                sys.stderr.write(f"[{label}] {line}\n")
                sys.stderr.flush()

    stderr_thread_read = threading.Thread(target=read_tar_stderr, daemon=True)
    stderr_thread_read.start()
    stderr_thread_write = threading.Thread(target=read_write_stderr, args=(tar_write, "tar-write"), daemon=True)
    stderr_thread_write.start()

    bytes_copied = 0
    buf_size = 131072
    last_update = 0.0
    last_bytes = 0
    last_speed_time = 0.0
    try:
        while True:
            buf = tar_read.stdout.read(buf_size)
            if not buf:
                break
            bytes_copied += len(buf)
            tar_write.stdin.write(buf)
            now = time.time()
            if now - last_update >= 0.2:
                last_update = now
                elapsed = now - start_time - paused_time
                elapsed_str = f"{int(elapsed//3600):02d}:{int((elapsed%3600)//60):02d}:{int(elapsed%60):02d}"
                bytes_str = format_bytes(bytes_copied)
                delta_bytes = bytes_copied - last_bytes
                delta_t = now - last_speed_time
                if delta_t > 0 and delta_bytes > 0:
                    speed_str = format_bytes(int(delta_bytes / delta_t)) + "/s"
                else:
                    speed_str = "0.00B/s"
                avg_speed = bytes_copied / elapsed if elapsed > 0 else 0
                avg_str = format_bytes(int(avg_speed)) + "/s"
                last_bytes = bytes_copied
                last_speed_time = now
                suffix = "  PAUSED" if paused else ""
                sys.stderr.write(f"\r{bytes_str:>12} {total_str:>12} {speed_str:>12} {avg_str:>12} {elapsed_str:>9}   {current_file}{suffix}")
                sys.stderr.flush()
    finally:
        tar_read.stdout.close()
        tar_write.stdin.close()

    pause_done.set()
    if paused:
        os.kill(tar_read.pid, signal.SIGCONT)
        os.kill(tar_write.pid, signal.SIGCONT)
        paused = False

    tar_read.wait()
    tar_write.wait()
    stderr_thread_read.join()
    stderr_thread_write.join()

    if tar_read.returncode != 0:
        print(f"\ntar read failed with exit code {tar_read.returncode}", file=sys.stderr)
        return tar_read.returncode
    if tar_write.returncode != 0:
        print(f"\ntar write failed with exit code {tar_write.returncode}", file=sys.stderr)
        return tar_write.returncode

    print(f"\nCopy complete: {source} -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
