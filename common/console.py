"""Single facade for all terminal output. Data -> stdout, chrome -> stderr."""

import json as _json
import os
import sys

from rich.console import Console
from rich.table import Table

_out = Console(file=sys.stdout)
_err = Console(file=sys.stderr, stderr=True)
_quiet = False


def configure(*, no_color: bool = False, quiet: bool = False, out_file=None, err_file=None) -> None:
    """Initializes output state. Called once by the Typer root callback."""
    global _out, _err, _quiet
    no_color = no_color or bool(os.environ.get("NO_COLOR"))
    _out = Console(
        file=out_file or sys.stdout,
        no_color=no_color,
        force_terminal=False if no_color else None,
    )
    _err = Console(
        file=err_file or sys.stderr,
        stderr=True,
        no_color=no_color,
        force_terminal=False if no_color else None,
    )
    _quiet = quiet


def print_json(obj, file=None) -> None:
    """Writes pure JSON to stdout (json.dumps, never rich)."""
    (file or sys.stdout).write(_json.dumps(obj, indent=2) + "\n")


def table(title: str, columns: list) -> Table:
    t = Table(title=title)
    for col in columns:
        t.add_column(col)
    return t


def print_table(t: Table) -> None:
    _out.print(t)


def print_tree(tree) -> None:
    _out.print(tree)


def status(msg: str) -> None:
    if not _quiet:
        _err.print(msg)


def success(msg: str) -> None:
    if not _quiet:
        _err.print(f"[green]✓[/green] {msg}")


def warn(msg: str) -> None:
    if not _quiet:
        _err.print(f"[yellow]![/yellow] {msg}")


def error(msg: str) -> None:
    _err.print(f"[red]Error:[/red] {msg}")


def confirm(prompt: str, default: bool = False) -> bool:
    from rich.prompt import Confirm

    return Confirm.ask(prompt, default=default, console=_err)


def prompt_choice(prompt: str, choices: list, default: str) -> str:
    from rich.prompt import Prompt

    return Prompt.ask(prompt, choices=choices, default=default, console=_err)


def progress():
    """Returns a rich Progress bound to stderr (context manager)."""
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    return Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=_err,
        disable=_quiet,
    )
