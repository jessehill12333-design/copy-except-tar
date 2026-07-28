#!/usr/bin/env python3
"""Copy a source directory to a destination, excluding specified subfolder paths."""

from __future__ import annotations

import argparse
import os
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


def build_rsync_command(source: Path, dest: Path, excludes: list[str], dry_run: bool) -> list[str]:
    cmd = ["rsync", "-a"]
    if dry_run:
        cmd.append("--dry-run")
        cmd.append("--info=progress2")
    else:
        cmd.append("--info=progress2,NAME")
    for ex in excludes:
        cmd.extend(["--exclude", ex])
    cmd.append(str(source))
    cmd.append(str(dest))
    return cmd


def confirm_yes(question: str) -> bool:
    try:
        answer = input(f"{question} [Y/n] ").strip().lower()
    except EOFError:
        return False
    return answer in ("", "y", "yes")


def print_banner() -> None:
    print("=" * 70)
    print("  copy-except — copy a directory excluding specified subfolders")
    print("  Uses rsync -a with --exclude for each excluded path.")
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
    show_summary(source, dest, excludes, dry_run)

    if not dry_run:
        if not confirm_yes("\nProceed with copy?"):
            print("Cancelled.")
            return 0

    cmd = build_rsync_command(source, dest, excludes, dry_run)
    print(f"\n{'DRY RUN: ' if dry_run else ''}Running: {' '.join(cmd)}")
    print()

    if dry_run:
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(f"\nrsync finished with exit code {result.returncode}", file=sys.stderr)
            return result.returncode
        print("\nDry run complete. No files were changed.")
        return 0

    start_time = time.time()
    print(f"{'Bytes':>16} {'%':>4} {'Speed':>12} {'ETA':>9} {'Elapsed':>9}   {'xfr#':>4} {'ir-chk':>6}   File", file=sys.stderr)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    current_file = ""

    def read_stream(stream, is_error: bool) -> int | None:
        nonlocal current_file
        for raw_line in iter(stream.readline, b''):
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            if is_error:
                sys.stderr.write(line + "\n")
                sys.stderr.flush()
            elif line.startswith("\r"):
                parts = line.split("\r")
                last = parts[-1].strip()
                if last:
                    elapsed = time.time() - start_time
                    elapsed_str = f"{int(elapsed//3600):02d}:{int((elapsed%3600)//60):02d}:{int(elapsed%60):02d}"
                    xfr_pos = last.find("(xfr#")
                    if xfr_pos != -1:
                        progress = last[:xfr_pos].strip()
                        rest = last[xfr_pos:]
                        sys.stderr.write(f"\r{progress} {elapsed_str} {rest}  {current_file}")
                    else:
                        sys.stderr.write(f"\r{last}  {elapsed_str}  {current_file}")
                    sys.stderr.flush()
            elif line.strip() and not line.startswith("created directory"):
                current_file = line
        return None

    threads = []
    for stream, is_err in [(proc.stdout, False), (proc.stderr, True)]:
        t = threading.Thread(target=read_stream, args=(stream, is_err), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    proc.wait()

    if proc.returncode != 0:
        print(f"\nrsync finished with exit code {proc.returncode}", file=sys.stderr)
        return proc.returncode

    print(f"\nCopy complete: {source} -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
