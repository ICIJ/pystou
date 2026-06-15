#!/usr/bin/env python3
"""Identify subcommand for detecting file types and mismatches."""

import logging
import os
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer

from common import console
from common.cli import (
    DbDirOpt,
    DirectoryArg,
    LogDirOpt,
    RecursiveOpt,
)
from common.fs_walker import is_excluded_dir
from common.logger import setup_logging
from common.validation import validate_directory_or_exit


class CheckKind(str, Enum):
    mismatch = "mismatch"
    encrypted = "encrypted"
    all = "all"


def identify_command(
    directory: DirectoryArg = ".",
    recursive: RecursiveOpt = False,
    check: Annotated[
        Optional[list[CheckKind]],
        typer.Option("--check", help="mismatch|encrypted|all (repeatable)."),
    ] = None,
    extensions: Annotated[
        Optional[str],
        typer.Option("--extensions", help="Comma-separated extensions to check (e.g. .zip,.pdf)."),
    ] = None,
    log_dir: LogDirOpt = ".",
    db_dir: DbDirOpt = ".",
) -> None:
    """Identify file-type mismatches and encrypted archives."""
    setup_logging("identify", log_dir)
    logging.info(
        {
            "action": "configuration",
            "command": "identify",
            "directory": directory,
            "recursive": recursive,
            "check": [c.value for c in check] if check else None,
            "extensions": extensions,
        }
    )
    validate_directory_or_exit(directory)

    # Determine which checks to run; default to all when nothing specified.
    checks = set(check) if check else {CheckKind.all}
    run_mismatch = CheckKind.mismatch in checks or CheckKind.all in checks
    run_encrypted = CheckKind.encrypted in checks or CheckKind.all in checks

    # Parse extensions filter if provided.
    extensions_filter: Optional[set[str]] = None
    if extensions:
        extensions_filter = {
            ext.strip().lower() if ext.startswith(".") else f".{ext.strip().lower()}"
            for ext in extensions.split(",")
        }

    files = collect_files(directory, recursive, extensions_filter)
    logging.info({"action": "files_found", "count": len(files)})

    issues: list[tuple[Path, str]] = []

    if run_mismatch:
        issues.extend(check_extension_mismatches(files))
    if run_encrypted:
        issues.extend(check_encrypted_archives(files))

    if not issues:
        console.status("No issues found.")
        logging.info({"action": "no_issues_found"})
        return

    t = console.table("Issues", ["Path", "Issue"])
    for file_path, issue in issues:
        t.add_row(str(file_path), issue)
    console.print_table(t)

    logging.info(
        {
            "action": "issues_found",
            "count": len(issues),
            "issues": [{"path": str(p), "issue": i} for p, i in issues],
        }
    )


# File signatures (magic bytes) for common file types
FILE_SIGNATURES: dict[bytes, str] = {
    b"\x50\x4b\x03\x04": "zip",
    b"\x50\x4b\x05\x06": "zip",  # Empty archive
    b"\x50\x4b\x07\x08": "zip",  # Spanned archive
    b"\x1f\x8b": "gzip",
    b"\x42\x5a\x68": "bzip2",
    b"\xfd\x37\x7a\x58\x5a\x00": "xz",
    b"\x28\xb5\x2f\xfd": "zstd",
    b"\x75\x73\x74\x61\x72": "tar",  # "ustar" at offset 257
    b"\x52\x61\x72\x21\x1a\x07": "rar",
    b"\x37\x7a\xbc\xaf\x27\x1c": "7z",
    b"\x21\x42\x44\x4e": "pst",  # MS Outlook PST
    b"\xff\xd8\xff": "jpeg",
    b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a": "png",
    b"\x47\x49\x46\x38": "gif",
    b"\x25\x50\x44\x46": "pdf",
    b"\x50\x4b": "docx/xlsx/pptx",  # Office Open XML (also zip-based)
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1": "doc/xls/ppt",  # OLE2 compound document
}

# Extension to expected type mapping
EXTENSION_TYPE_MAP: dict[str, set[str]] = {
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
    ".ost": {"pst"},  # OST shares the PST !BDN signature; cannot differ by magic
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


def collect_files(
    directory: str,
    recursive: bool,
    extensions_filter: Optional[set[str]] = None,
) -> list[Path]:
    """Collects files from the directory.

    Args:
        directory: Directory to scan.
        recursive: Whether to scan recursively.
        extensions_filter: Optional set of extensions to filter by.

    Returns:
        List of file paths.
    """
    files: list[Path] = []
    directory_path = Path(directory)

    if recursive:
        # followlinks=False prevents infinite loops from symlink cycles
        for root, dirs, filenames in os.walk(directory_path, followlinks=False):
            # Prune the trash directory: removes it from results and prevents descent.
            dirs[:] = [d for d in dirs if not is_excluded_dir(d)]
            root_path = Path(root)

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
                # Skip the trash directory
                if entry.is_dir(follow_symlinks=False) and is_excluded_dir(entry.name):
                    continue
                if entry.is_file(follow_symlinks=False):
                    file_path = Path(entry.path)
                    if extensions_filter is None or file_path.suffix.lower() in extensions_filter:
                        files.append(file_path)
        except PermissionError as e:
            console.error(f"Permission denied: {directory_path}")
            logging.warning({"action": "scan_error", "path": str(directory_path), "error": str(e)})

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
        logging.warning(
            {
                "action": "detect_type",
                "status": "permission_denied",
                "path": str(file_path),
            }
        )
        return None
    except OSError as e:
        logging.warning(
            {
                "action": "detect_type",
                "status": "error",
                "path": str(file_path),
                "error": str(e),
            }
        )
        return None


def check_extension_mismatches(files: list[Path]) -> list[tuple[Path, str]]:
    """Checks for files with mismatched extensions.

    Args:
        files: List of files to check.

    Returns:
        List of (path, issue description) tuples.
    """
    issues: list[tuple[Path, str]] = []

    for file_path in files:
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
            logging.warning(
                {
                    "action": "extension_mismatch",
                    "path": str(file_path),
                    "extension": ext,
                    "detected_type": detected_type,
                }
            )

    return issues


def check_encrypted_archives(files: list[Path]) -> list[tuple[Path, str]]:
    """Checks for encrypted ZIP archives.

    Args:
        files: List of files to check.

    Returns:
        List of (path, issue description) tuples.
    """
    import zipfile

    issues: list[tuple[Path, str]] = []
    zip_extensions = {".zip", ".docx", ".xlsx", ".pptx"}

    for file_path in files:
        if file_path.suffix.lower() not in zip_extensions:
            continue

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                for info in zf.infolist():
                    if info.flag_bits & 0x1:  # Encrypted flag
                        issue = "Encrypted ZIP archive"
                        issues.append((file_path, issue))
                        logging.warning(
                            {
                                "action": "encrypted_archive",
                                "path": str(file_path),
                            }
                        )
                        break

        except FileNotFoundError:
            logging.warning(
                {
                    "action": "check_encrypted",
                    "status": "not_found",
                    "path": str(file_path),
                }
            )
        except PermissionError:
            logging.warning(
                {
                    "action": "check_encrypted",
                    "status": "permission_denied",
                    "path": str(file_path),
                }
            )
        except zipfile.BadZipFile:
            # Not a valid zip file - might be detected by mismatch check
            pass
        except OSError as e:
            logging.warning(
                {
                    "action": "check_encrypted",
                    "status": "error",
                    "path": str(file_path),
                    "error": str(e),
                }
            )

    return issues
