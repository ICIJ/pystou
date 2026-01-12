#!/usr/bin/env python3
"""Stats subcommand for displaying directory statistics."""

import argparse
import heapq
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional

from common.logger import setup_logging
from common.cli import add_common_arguments
from common.cursor import hide_cursor, show_cursor


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

    # Validate directory
    directory_path = Path(args.directory)
    if not directory_path.exists():
        print(f"Error: Directory does not exist: {args.directory}")
        logging.error({"action": "error", "message": "Directory not found", "path": args.directory})
        sys.exit(1)
    if not directory_path.is_dir():
        print(f"Error: Not a directory: {args.directory}")
        logging.error({"action": "error", "message": "Not a directory", "path": args.directory})
        sys.exit(1)

    # Collect statistics
    hide_cursor()
    try:
        stats = collect_stats(args.directory, args.recursive, args.top)
    except KeyboardInterrupt:
        show_cursor()
        print("\nScan interrupted by user.")
        logging.info({"action": "scan_interrupted"})
        sys.exit(130)
    show_cursor()

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


def collect_stats(directory: str, recursive: bool, top_n: int = 10) -> Dict:
    """Collects statistics from the directory.

    Args:
        directory: Directory to analyze.
        recursive: Whether to analyze recursively.
        top_n: Number of top files to track (for memory efficiency).

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
            "symlinks_skipped": 0,
            "errors": 0,
        },
        "by_extension": defaultdict(lambda: {"count": 0, "size": 0}),
        "largest_files": [],  # Will be a heap of (size, path) tuples
        "empty_directories": [],
    }

    archive_extensions = {
        ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz",
        ".zst", ".rar", ".7z", ".pst",
    }

    directory_path = Path(directory)
    scanned = 0

    if recursive:
        # followlinks=False prevents infinite loops from symlink cycles
        for root, dirs, files in os.walk(directory_path, followlinks=False):
            root_path = Path(root)
            scanned += 1

            # Progress indicator every 1000 directories
            if scanned % 1000 == 0:
                print(f"Scanned {scanned} directories, {stats['summary']['total_files']} files...", end="\r")

            stats["summary"]["total_dirs"] += len(dirs)

            # Check for empty directories
            for d in dirs:
                dir_path = root_path / d
                # Skip symlinks
                if dir_path.is_symlink():
                    stats["summary"]["symlinks_skipped"] += 1
                    continue
                try:
                    if not any(dir_path.iterdir()):
                        stats["summary"]["empty_dirs"] += 1
                        if len(stats["empty_directories"]) < top_n:
                            stats["empty_directories"].append(str(dir_path))
                except PermissionError:
                    stats["summary"]["errors"] += 1
                except FileNotFoundError:
                    # Directory deleted between listing and checking
                    pass

            # Process files
            for filename in files:
                file_path = root_path / filename
                # Skip symlinks
                if file_path.is_symlink():
                    stats["summary"]["symlinks_skipped"] += 1
                    continue
                process_file(file_path, stats, archive_extensions, top_n)
    else:
        try:
            for entry in os.scandir(directory_path):
                # Skip symlinks
                if entry.is_symlink():
                    stats["summary"]["symlinks_skipped"] += 1
                    continue

                if entry.is_dir(follow_symlinks=False):
                    stats["summary"]["total_dirs"] += 1
                    try:
                        if not any(Path(entry.path).iterdir()):
                            stats["summary"]["empty_dirs"] += 1
                            if len(stats["empty_directories"]) < top_n:
                                stats["empty_directories"].append(entry.path)
                    except PermissionError:
                        stats["summary"]["errors"] += 1
                    except FileNotFoundError:
                        pass
                elif entry.is_file(follow_symlinks=False):
                    process_file(Path(entry.path), stats, archive_extensions, top_n)
        except PermissionError as e:
            print(f"Permission denied: {directory_path}")
            logging.warning({"action": "scan_error", "path": str(directory_path), "error": str(e)})
            stats["summary"]["errors"] += 1

    if scanned >= 1000:
        print(f"Scanned {scanned} directories, {stats['summary']['total_files']} files.    ")

    # Convert heap to sorted list (largest first)
    stats["largest_files"] = [
        (path, size) for size, path in sorted(stats["largest_files"], reverse=True)
    ]

    return stats


def process_file(file_path: Path, stats: Dict, archive_extensions: set, top_n: int) -> None:
    """Processes a single file and updates statistics.

    Args:
        file_path: Path to the file.
        stats: Statistics dictionary to update.
        archive_extensions: Set of archive file extensions.
        top_n: Number of largest files to track.
    """
    try:
        size = file_path.stat().st_size
    except FileNotFoundError:
        # File deleted between listing and stat
        return
    except PermissionError:
        stats["summary"]["errors"] += 1
        return
    except OSError:
        stats["summary"]["errors"] += 1
        return

    stats["summary"]["total_files"] += 1
    stats["summary"]["total_size"] += size

    ext = file_path.suffix.lower() or "(no extension)"
    stats["by_extension"][ext]["count"] += 1
    stats["by_extension"][ext]["size"] += size

    if ext in archive_extensions:
        stats["summary"]["archive_files"] += 1

    # Use a min-heap to efficiently track top N largest files
    # We store (size, path) and keep only the largest N
    if len(stats["largest_files"]) < top_n:
        heapq.heappush(stats["largest_files"], (size, str(file_path)))
    elif size > stats["largest_files"][0][0]:
        heapq.heapreplace(stats["largest_files"], (size, str(file_path)))


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

    if summary["symlinks_skipped"] > 0:
        print(f"Symlinks skipped:  {summary['symlinks_skipped']:,}")
    if summary["errors"] > 0:
        print(f"Errors:            {summary['errors']:,}")

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
        for file_path, size in stats["largest_files"][:top_n]:
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
            for path, size in stats["largest_files"][:top_n]
        ],
        "empty_directories": stats["empty_directories"][:top_n],
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
