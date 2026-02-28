#!/usr/bin/env python3
"""Create a project backup zip while excluding noisy and oversized files."""

from __future__ import annotations

import argparse
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a filtered project backup zip")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    parser.add_argument(
        "--exclude-file",
        type=Path,
        default=Path("backup.exclude"),
        help="Path to file with glob exclude patterns",
    )
    parser.add_argument(
        "--max-size-mb",
        type=float,
        default=25.0,
        help="Skip files larger than this size in MiB",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output zip path (default: backups/<project>_backup_<timestamp>.zip)",
    )
    return parser.parse_args()


def load_patterns(path: Path) -> list[str]:
    if not path.exists():
        return []
    patterns: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def normalize(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_excluded(rel_path: str, patterns: list[str]) -> bool:
    parts = rel_path.split("/")

    for pattern in patterns:
        norm_pattern = pattern.strip()
        if not norm_pattern:
            continue

        if norm_pattern.endswith("/"):
            base = norm_pattern[:-1]
            if rel_path == base or rel_path.startswith(base + "/"):
                return True
            continue

        if fnmatch(rel_path, norm_pattern):
            return True

        # Let basename-only globs like "*.log" work in any folder.
        if "/" not in norm_pattern and any(fnmatch(part, norm_pattern) for part in parts):
            return True

    return False


def default_output(root: Path) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return root / "backups" / f"{root.name}_backup_{timestamp}.zip"


def main() -> int:
    args = parse_args()
    root = args.root.resolve()

    exclude_file = args.exclude_file
    if not exclude_file.is_absolute():
        exclude_file = root / exclude_file

    output = args.output if args.output is not None else default_output(root)
    if not output.is_absolute():
        output = root / output

    max_size_bytes = int(args.max_size_mb * 1024 * 1024)

    patterns = load_patterns(exclude_file)
    # Safety excludes to avoid recursive archives and VCS internals.
    for required in (".git/", "backups/"):
        if required not in patterns:
            patterns.append(required)

    output.parent.mkdir(parents=True, exist_ok=True)

    included = 0
    skipped_pattern = 0
    skipped_size = 0

    with ZipFile(output, "w", compression=ZIP_DEFLATED) as zf:
        for path in root.rglob("*"):
            if not path.is_file():
                continue

            rel = normalize(path, root)

            if rel == normalize(output, root):
                continue

            if is_excluded(rel, patterns):
                skipped_pattern += 1
                continue

            size = path.stat().st_size
            if size > max_size_bytes:
                skipped_size += 1
                continue

            zf.write(path, arcname=rel)
            included += 1

    print(f"Backup created: {output}")
    print(f"Included files: {included}")
    print(f"Skipped by exclude patterns: {skipped_pattern}")
    print(f"Skipped by max size ({args.max_size_mb} MiB): {skipped_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
