#!/usr/bin/env python3
"""PyStou CLI (Typer)."""

import logging

import typer

from cleanup.main import cleanup_command
from common import console
from common.errors import PystouError
from dedup_folders.main import dedup_command
from doctor.main import doctor_command
from empty.main import empty_command
from extract.main import extract_command
from identify.main import identify_command
from pystou import __version__
from restore.main import restore_command
from stats.main import stats_command
from trash.main import trash_app

app = typer.Typer(
    no_args_is_help=True, add_completion=True, help="PyStou — tidy large filesystems."
)
app.command("cleanup")(cleanup_command)
app.command("dedup")(dedup_command)
app.command("extract")(extract_command)
app.command("identify")(identify_command)
app.command("stats")(stats_command)
app.command("empty")(empty_command)
app.command("restore")(restore_command)
app.command("doctor")(doctor_command)
app.add_typer(trash_app, name="trash", help="List or purge quarantined files.")


def _version_cb(value: bool):
    if value:
        typer.echo(f"pystou {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(False, "--version", callback=_version_cb, is_eager=True),
    no_color: bool = typer.Option(False, "--no-color", help="Disable colored output."),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Suppress progress/status."),
):
    console.configure(no_color=no_color, quiet=quiet)


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        console.warn("Interrupted by user.")
        raise SystemExit(130) from None
    except PystouError as e:
        console.error(str(e))
        logging.error({"action": "fatal", "error": str(e)})
        raise SystemExit(1) from None
    except Exception as e:  # top-level boundary
        logging.error({"action": "unexpected_error", "error": str(e)}, exc_info=True)
        console.error(f"Unexpected error: {e}\nSee the log file for details.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
