#!/usr/bin/env python3
"""Doctor subcommand: preflight check of required external CLI tools."""

import importlib.util
import shutil
import subprocess
from dataclasses import dataclass
from typing import Annotated, Optional

import typer

from common import console


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


def doctor_command(
    json_out: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Check that required external tools are installed."""
    statuses = check_environment()

    if json_out:
        console.print_json(
            [
                {
                    "name": s.name,
                    "available": s.available,
                    "version": s.version,
                    "enables": s.enables,
                    "install_hint": s.install_hint,
                }
                for s in statuses
            ]
        )
    else:
        t = console.table("Environment", ["Tool", "Status", "Version", "Enables"])
        for s in statuses:
            status_str = "[green]✓ found[/green]" if s.available else "[red]✗ missing[/red]"
            t.add_row(s.name, status_str, s.version or "", s.enables)
        console.print_table(t)
        for s in statuses:
            if not s.available:
                console.status(f"  Install hint for {s.name}: {s.install_hint}")

    raise typer.Exit(0 if all(s.available for s in statuses) else 1)
