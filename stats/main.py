#!/usr/bin/env python3
"""Stats subcommand for displaying directory statistics."""

import argparse
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional

from common.logger import setup_logging
from common.cli import add_common_arguments


def add_stats_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds stats-specific arguments to the parser.

    Args:
        parser: ArgumentParser to add arguments to.
    """
    add_common_arguments(parser)
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="Number of top items to show (default: 10)",
    )
    parser.add_argument(
        "--by-extension",
        action="store_true",
        help="Show breakdown by file extension",
    )
    parser.add_argument(
        "--by-size",
        action="store_true",
        help="Show largest files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output statistics in JSON format",
    )


def main(args: Optional[argparse.Namespace] = None) -> None:
    """Main entry point for stats.

    Args:
        args: Parsed arguments. If None, parses from command line.
    """
    if args is None:
        parser = argparse.ArgumentParser(description="Directory statistics script.")
        add_stats_arguments(parser)
        args = parser.parse_args()

    setup_logging("stats", args.log_dir)
    log_configuration(args)

    # Collect statistics
    stats = collect_stats(args.directory, args.recursive)

    if args.json:
        output_json(stats, args.top)
    else:
        output_text(stats, args.top, args.by_extension, args.by_size)

    logging.info({"action": "stats_complete", **stats["summary"]})


def log_configuration(args) -> None:
    """Logs the configuration used to run the script."""
    config = {
        k: v for k, v in vars(args).items()
        if not k.startswith("_") and k not in ("func", "command")
    }
    config["action"] = "configuration"
    logging.info(config)


def collect_stats(directory: str, recursive: bool) -> Dict:
    """Collects statistics from the directory.

    Args:
        directory: Directory to analyze.
        recursive: Whether to analyze recursively.

    Returns:
        Dictionary with collected statistics.
    """
    stats = {
        "summary": {
            "total_files": 0,
            "total_dirs": 0,
            "total_size": 0,
            "empty_dirs": 0,
            "archive_files": 0,
        },
        "by_extension": defaultdict(lambda: {"count": 0, "size": 0}),
        "files_by_size": [],
        "empty_directories": [],
    }

    archive_extensions = {
        ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz",
        ".zst", ".rar", ".7z", ".pst",
    }

    directory_path = Path(directory)

    if recursive:
        for root, dirs, files in os.walk(directory_path):
            root_path = Path(root)
            stats["summary"]["total_dirs"] += len(dirs)

            # Check for empty directories
            for d in dirs:
                dir_path = root_path / d
                try:
                    if not any(dir_path.iterdir()):
                        stats["summary"]["empty_dirs"] += 1
                        stats["empty_directories"].append(str(dir_path))
                except PermissionError:
                    pass

            # Process files
            for filename in files:
                file_path = root_path / filename
                process_file(file_path, stats, archive_extensions)
    else:
        for entry in os.scandir(directory_path):
            if entry.is_dir():
                stats["summary"]["total_dirs"] += 1
                try:
                    if not any(Path(entry.path).iterdir()):
                        stats["summary"]["empty_dirs"] += 1
                        stats["empty_directories"].append(entry.path)
                except PermissionError:
                    pass
            elif entry.is_file():
                process_file(Path(entry.path), stats, archive_extensions)

    # Sort files by size descending
    stats["files_by_size"].sort(key=lambda x: x[1], reverse=True)

    return stats


def process_file(file_path: Path, stats: Dict, archive_extensions: set) -> None:
    """Processes a single file and updates statistics.

    Args:
        file_path: Path to the file.
        stats: Statistics dictionary to update.
        archive_extensions: Set of archive file extensions.
    """
    try:
        size = file_path.stat().st_size
    except (OSError, PermissionError):
        return

    stats["summary"]["total_files"] += 1
    stats["summary"]["total_size"] += size

    ext = file_path.suffix.lower() or "(no extension)"
    stats["by_extension"][ext]["count"] += 1
    stats["by_extension"][ext]["size"] += size

    if ext in archive_extensions:
        stats["summary"]["archive_files"] += 1

    stats["files_by_size"].append((str(file_path), size))


def format_size(size: int) -> str:
    """Formats a size in bytes to human-readable format.

    Args:
        size: Size in bytes.

    Returns:
        Human-readable size string.
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def output_text(
    stats: Dict,
    top_n: int,
    show_by_extension: bool,
    show_by_size: bool,
) -> None:
    """Outputs statistics in text format.

    Args:
        stats: Collected statistics.
        top_n: Number of top items to show.
        show_by_extension: Whether to show extension breakdown.
        show_by_size: Whether to show largest files.
    """
    summary = stats["summary"]

    print("\n=== Directory Statistics ===\n")
    print(f"Total files:       {summary['total_files']:,}")
    print(f"Total directories: {summary['total_dirs']:,}")
    print(f"Total size:        {format_size(summary['total_size'])}")
    print(f"Archive files:     {summary['archive_files']:,}")
    print(f"Empty directories: {summary['empty_dirs']:,}")

    # Show extension breakdown if requested or by default
    if show_by_extension or (not show_by_extension and not show_by_size):
        print(f"\n--- Top {top_n} Extensions by Count ---\n")
        sorted_by_count = sorted(
            stats["by_extension"].items(),
            key=lambda x: x[1]["count"],
            reverse=True,
        )[:top_n]

        for ext, data in sorted_by_count:
            print(f"  {ext:15} {data['count']:>8,} files  ({format_size(data['size']):>10})")

    # Show largest files if requested
    if show_by_size:
        print(f"\n--- Top {top_n} Largest Files ---\n")
        for file_path, size in stats["files_by_size"][:top_n]:
            print(f"  {format_size(size):>10}  {file_path}")

    # Show empty directories if any
    if summary["empty_dirs"] > 0 and summary["empty_dirs"] <= top_n:
        print(f"\n--- Empty Directories ({summary['empty_dirs']}) ---\n")
        for dir_path in stats["empty_directories"][:top_n]:
            print(f"  {dir_path}")


def output_json(stats: Dict, top_n: int) -> None:
    """Outputs statistics in JSON format.

    Args:
        stats: Collected statistics.
        top_n: Number of top items to include.
    """
    import json

    output = {
        "summary": stats["summary"],
        "by_extension": dict(stats["by_extension"]),
        "largest_files": [
            {"path": path, "size": size}
            for path, size in stats["files_by_size"][:top_n]
        ],
        "empty_directories": stats["empty_directories"][:top_n],
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
