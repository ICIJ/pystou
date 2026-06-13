#!/usr/bin/env python3
"""Doctor subcommand: preflight check of required external CLI tools."""

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class ToolStatus:
    """Availability of an external tool PyStou relies on.

    Attributes:
        name: The tool's command name.
        available: Whether the capability is available.
        version: A best-effort version string, or None if unknown.
        enables: A short description of what the tool enables.
        install_hint: How to install the tool if it is missing.
    """

    name: str
    available: bool
    version: Optional[str]
    enables: str
    install_hint: str


def _zstandard_module_available() -> bool:
    """Reports whether the Python ``zstandard`` module can be imported.

    Returns:
        True if the module is importable, False otherwise.
    """
    return importlib.util.find_spec("zstandard") is not None


def _tool_version(name: str) -> Optional[str]:
    """Returns a best-effort version string for a CLI tool.

    Runs ``<name> --version`` and returns the first non-empty output line.
    Never raises: any OSError or subprocess error yields None.

    Args:
        name: The tool's command name.

    Returns:
        The first non-empty line of version output, or None.
    """
    try:
        result = subprocess.run(
            [name, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    for line in output.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def check_environment() -> list[ToolStatus]:
    """Checks the external tools PyStou needs and returns their statuses.

    Returns:
        A list of ToolStatus for readpst, 7z, and zstd. The zstd capability
        is available when the ``zstd`` CLI is present OR the Python
        ``zstandard`` module is importable.
    """
    statuses: list[ToolStatus] = []

    # readpst — PST archives
    readpst_available = shutil.which("readpst") is not None
    statuses.append(
        ToolStatus(
            name="readpst",
            available=readpst_available,
            version=_tool_version("readpst") if readpst_available else None,
            enables="PST archives (.pst)",
            install_hint="Install pst-utils (apt install pst-utils / brew install libpst).",
        )
    )

    # 7z — split ZIP archives
    sevenzip_available = shutil.which("7z") is not None
    statuses.append(
        ToolStatus(
            name="7z",
            available=sevenzip_available,
            version=_tool_version("7z") if sevenzip_available else None,
            enables="split ZIP archives (.z01, .z02, ...)",
            install_hint="Install p7zip-full (apt install p7zip-full / brew install p7zip).",
        )
    )

    # zstd — Zstandard archives (CLI or Python module)
    zstd_cli = shutil.which("zstd") is not None
    zstd_module = _zstandard_module_available()
    if zstd_cli:
        zstd_version = _tool_version("zstd")
    elif zstd_module:
        zstd_version = "python zstandard module"
    else:
        zstd_version = None
    statuses.append(
        ToolStatus(
            name="zstd",
            available=zstd_cli or zstd_module,
            version=zstd_version,
            enables="Zstandard archives (.zst, .tar.zst)",
            install_hint=(
                "Install zstd (apt install zstd / brew install zstd) or pip install zstandard."
            ),
        )
    )

    return statuses


def add_doctor_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds doctor-specific arguments to the parser.

    Args:
        parser: ArgumentParser to add arguments to.
    """
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the report as a JSON array",
    )


def _print_human_report(statuses: list[ToolStatus]) -> None:
    """Prints a human-readable report for the tool statuses.

    Args:
        statuses: The tool statuses to report.
    """
    for status in statuses:
        mark = "✓" if status.available else "✗"
        version = f" ({status.version})" if status.version else ""
        print(f"{mark} {status.name}{version} - enables {status.enables}")
        if not status.available:
            print(f"    {status.install_hint}")

    available_count = sum(1 for s in statuses if s.available)
    total = len(statuses)
    print()
    print(f"{available_count} of {total} capabilities available.")
    if available_count < total:
        print("Missing tools only affect the matching archive formats.")


def main(args: Optional[argparse.Namespace] = None) -> int:
    """Main entry point for doctor.

    Args:
        args: Parsed arguments. If None, parses from command line.

    Returns:
        0 if all capabilities are available, 1 otherwise.
    """
    if args is None:
        parser = argparse.ArgumentParser(
            description="Check that required external tools are installed."
        )
        add_doctor_arguments(parser)
        args = parser.parse_args()

    statuses = check_environment()

    if args.json:
        payload = [
            {
                "name": s.name,
                "available": s.available,
                "version": s.version,
                "enables": s.enables,
                "install_hint": s.install_hint,
            }
            for s in statuses
        ]
        print(json.dumps(payload, indent=2))
    else:
        _print_human_report(statuses)

    all_available = all(s.available for s in statuses)
    return 0 if all_available else 1


if __name__ == "__main__":
    sys.exit(main())
