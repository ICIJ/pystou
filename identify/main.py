#!/usr/bin/env python3
"""Identify subcommand for detecting file types and mismatches."""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from common.logger import setup_logging
from common.cli import add_common_arguments

# File signatures (magic bytes) for common file types
FILE_SIGNATURES: Dict[bytes, str] = {
    b"\x50\x4B\x03\x04": "zip",
    b"\x50\x4B\x05\x06": "zip",  # Empty archive
    b"\x50\x4B\x07\x08": "zip",  # Spanned archive
    b"\x1F\x8B": "gzip",
    b"\x42\x5A\x68": "bzip2",
    b"\xFD\x37\x7A\x58\x5A\x00": "xz",
    b"\x28\xB5\x2F\xFD": "zstd",
    b"\x75\x73\x74\x61\x72": "tar",  # "ustar" at offset 257
    b"\x52\x61\x72\x21\x1A\x07": "rar",
    b"\x37\x7A\xBC\xAF\x27\x1C": "7z",
    b"\x21\x42\x44\x4E": "pst",  # MS Outlook PST
    b"\xFF\xD8\xFF": "jpeg",
    b"\x89\x50\x4E\x47\x0D\x0A\x1A\x0A": "png",
    b"\x47\x49\x46\x38": "gif",
    b"\x25\x50\x44\x46": "pdf",
    b"\x50\x4B": "docx/xlsx/pptx",  # Office Open XML (also zip-based)
    b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1": "doc/xls/ppt",  # OLE2 compound document
}

# Extension to expected type mapping
EXTENSION_TYPE_MAP: Dict[str, Set[str]] = {
    ".zip": {"zip", "docx/xlsx/pptx"},
    ".gz": {"gzip"},
    ".tgz": {"gzip"},
    ".bz2": {"bzip2"},
    ".xz": {"xz"},
    ".zst": {"zstd"},
    ".tar": {"tar"},
    ".rar": {"rar"},
    ".7z": {"7z"},
    ".pst": {"pst"},
    ".jpg": {"jpeg"},
    ".jpeg": {"jpeg"},
    ".png": {"png"},
    ".gif": {"gif"},
    ".pdf": {"pdf"},
    ".docx": {"zip", "docx/xlsx/pptx"},
    ".xlsx": {"zip", "docx/xlsx/pptx"},
    ".pptx": {"zip", "docx/xlsx/pptx"},
    ".doc": {"doc/xls/ppt"},
    ".xls": {"doc/xls/ppt"},
    ".ppt": {"doc/xls/ppt"},
}


def add_identify_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds identify-specific arguments to the parser.

    Args:
        parser: ArgumentParser to add arguments to.
    """
    add_common_arguments(parser)
    parser.add_argument(
        "--check-mismatch",
        action="store_true",
        help="Check for files with mismatched extensions",
    )
    parser.add_argument(
        "--check-encrypted",
        action="store_true",
        help="Check for encrypted ZIP archives",
    )
    parser.add_argument(
        "--check-all",
        action="store_true",
        help="Run all checks (mismatch, encrypted)",
    )
    parser.add_argument(
        "--extensions",
        type=str,
        metavar="EXT",
        help="Comma-separated list of extensions to check (e.g., '.zip,.pdf')",
    )


def main(args: Optional[argparse.Namespace] = None) -> None:
    """Main entry point for identify.

    Args:
        args: Parsed arguments. If None, parses from command line.
    """
    if args is None:
        parser = argparse.ArgumentParser(description="Identify file types script.")
        add_identify_arguments(parser)
        args = parser.parse_args()

    setup_logging("identify", args.log_dir)
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

    # Enable all checks if --check-all is set
    if args.check_all:
        args.check_mismatch = True
        args.check_encrypted = True

    # Default to mismatch check if no specific check is requested
    if not args.check_mismatch and not args.check_encrypted:
        args.check_mismatch = True

    # Parse extensions filter if provided
    extensions_filter: Optional[Set[str]] = None
    if args.extensions:
        extensions_filter = {
            ext.strip().lower() if ext.startswith(".") else f".{ext.strip().lower()}"
            for ext in args.extensions.split(",")
        }

    # Collect files to analyze
    try:
        files = collect_files(args.directory, args.recursive, extensions_filter)
    except KeyboardInterrupt:
        print("\nScan interrupted by user.")
        logging.info({"action": "scan_interrupted"})
        sys.exit(130)

    print(f"Found {len(files)} files to analyze.")
    logging.info({"action": "files_found", "count": len(files)})

    if not files:
        print("No files to analyze.")
        return

    issues: List[Tuple[Path, str]] = []

    # Run checks
    try:
        if args.check_mismatch:
            print("Checking for extension mismatches...")
            mismatch_issues = check_extension_mismatches(files)
            issues.extend(mismatch_issues)

        if args.check_encrypted:
            print("Checking for encrypted archives...")
            encrypted_issues = check_encrypted_archives(files)
            issues.extend(encrypted_issues)
    except KeyboardInterrupt:
        print("\nAnalysis interrupted by user.")
        logging.info({"action": "analysis_interrupted"})
        sys.exit(130)

    # Report results
    if not issues:
        print("No issues found.")
        logging.info({"action": "no_issues_found"})
        return

    print(f"\nFound {len(issues)} issue(s):\n")
    for file_path, issue in issues:
        print(f"  [{issue}] {file_path}")

    logging.info({
        "action": "issues_found",
        "count": len(issues),
        "issues": [{"path": str(p), "issue": i} for p, i in issues],
    })


def log_configuration(args) -> None:
    """Logs the configuration used to run the script."""
    config = {
        k: v for k, v in vars(args).items()
        if not k.startswith("_") and k not in ("func", "command")
    }
    config["action"] = "configuration"
    logging.info(config)


def collect_files(
    directory: str,
    recursive: bool,
    extensions_filter: Optional[Set[str]] = None,
) -> List[Path]:
    """Collects files from the directory.

    Args:
        directory: Directory to scan.
        recursive: Whether to scan recursively.
        extensions_filter: Optional set of extensions to filter by.

    Returns:
        List of file paths.
    """
    files: List[Path] = []
    directory_path = Path(directory)
    scanned = 0

    if recursive:
        # followlinks=False prevents infinite loops from symlink cycles
        for root, _, filenames in os.walk(directory_path, followlinks=False):
            root_path = Path(root)
            scanned += 1

            # Progress indicator every 1000 directories
            if scanned % 1000 == 0:
                print(f"  Scanned {scanned} directories...", end="\r")

            for filename in filenames:
                file_path = root_path / filename
                # Skip symlinks
                if file_path.is_symlink():
                    continue
                if extensions_filter is None or file_path.suffix.lower() in extensions_filter:
                    files.append(file_path)
    else:
        try:
            for entry in os.scandir(directory_path):
                # Skip symlinks
                if entry.is_symlink():
                    continue
                if entry.is_file(follow_symlinks=False):
                    file_path = Path(entry.path)
                    if extensions_filter is None or file_path.suffix.lower() in extensions_filter:
                        files.append(file_path)
        except PermissionError as e:
            print(f"Permission denied: {directory_path}")
            logging.warning({"action": "scan_error", "path": str(directory_path), "error": str(e)})

    if scanned >= 1000:
        print(f"  Scanned {scanned} directories.    ")  # Clear progress line

    return files


def detect_file_type(file_path: Path) -> Optional[str]:
    """Detects the actual file type by reading magic bytes.

    Args:
        file_path: Path to the file.

    Returns:
        Detected file type or None if unknown.
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)

        if len(header) == 0:
            return None

        # Check for tar (magic at offset 257)
        if len(header) >= 8:
            try:
                with open(file_path, "rb") as f:
                    f.seek(257)
                    tar_magic = f.read(5)
                    if tar_magic == b"ustar":
                        return "tar"
            except OSError:
                pass

        # Check against known signatures
        for signature, file_type in FILE_SIGNATURES.items():
            if header.startswith(signature):
                return file_type

        return None

    except FileNotFoundError:
        logging.warning({"action": "detect_type", "status": "not_found", "path": str(file_path)})
        return None
    except PermissionError:
        logging.warning({"action": "detect_type", "status": "permission_denied", "path": str(file_path)})
        return None
    except OSError as e:
        logging.warning({"action": "detect_type", "status": "error", "path": str(file_path), "error": str(e)})
        return None


def check_extension_mismatches(files: List[Path]) -> List[Tuple[Path, str]]:
    """Checks for files with mismatched extensions.

    Args:
        files: List of files to check.

    Returns:
        List of (path, issue description) tuples.
    """
    issues: List[Tuple[Path, str]] = []
    total = len(files)

    for i, file_path in enumerate(files, 1):
        # Progress indicator
        if total > 100 and i % 100 == 0:
            print(f"  Checked {i}/{total} files...", end="\r")

        ext = file_path.suffix.lower()
        if ext not in EXTENSION_TYPE_MAP:
            continue

        expected_types = EXTENSION_TYPE_MAP[ext]
        detected_type = detect_file_type(file_path)

        if detected_type is None:
            # Could not detect type - might be empty or unknown format
            continue

        if detected_type not in expected_types:
            issue = f"Extension mismatch: {ext} file is actually {detected_type}"
            issues.append((file_path, issue))
            logging.warning({
                "action": "extension_mismatch",
                "path": str(file_path),
                "extension": ext,
                "detected_type": detected_type,
            })

    if total > 100:
        print(f"  Checked {total} files.           ")  # Clear progress line

    return issues


def check_encrypted_archives(files: List[Path]) -> List[Tuple[Path, str]]:
    """Checks for encrypted ZIP archives.

    Args:
        files: List of files to check.

    Returns:
        List of (path, issue description) tuples.
    """
    import zipfile

    issues: List[Tuple[Path, str]] = []
    zip_extensions = {".zip", ".docx", ".xlsx", ".pptx"}
    checked = 0

    for i, file_path in enumerate(files, 1):
        if file_path.suffix.lower() not in zip_extensions:
            continue

        checked += 1

        # Progress indicator
        if checked > 100 and checked % 100 == 0:
            print(f"  Checked {checked} archives...", end="\r")

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                for info in zf.infolist():
                    if info.flag_bits & 0x1:  # Encrypted flag
                        issue = "Encrypted ZIP archive"
                        issues.append((file_path, issue))
                        logging.warning({
                            "action": "encrypted_archive",
                            "path": str(file_path),
                        })
                        break

        except FileNotFoundError:
            logging.warning({"action": "check_encrypted", "status": "not_found", "path": str(file_path)})
        except PermissionError:
            logging.warning({"action": "check_encrypted", "status": "permission_denied", "path": str(file_path)})
        except zipfile.BadZipFile:
            # Not a valid zip file - might be detected by mismatch check
            pass
        except OSError as e:
            logging.warning({"action": "check_encrypted", "status": "error", "path": str(file_path), "error": str(e)})

    if checked > 100:
        print(f"  Checked {checked} archives.      ")  # Clear progress line

    return issues


if __name__ == "__main__":
    main()
