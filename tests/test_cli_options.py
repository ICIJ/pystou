import unittest

import typer
from typer.testing import CliRunner

from common.cli import DbDirOpt, DirectoryArg, DryRunOpt, LogDirOpt, RecursiveOpt


class TestSharedOptions(unittest.TestCase):
    def test_options_parse(self):
        app = typer.Typer()

        @app.command()
        def cmd(
            directory: DirectoryArg = ".",
            recursive: RecursiveOpt = False,
            dry_run: DryRunOpt = False,
            log_dir: LogDirOpt = ".",
            db_dir: DbDirOpt = ".",
        ):
            typer.echo(f"{directory}|{recursive}|{dry_run}|{log_dir}|{db_dir}")

        r = CliRunner().invoke(app, ["/tmp", "-r", "-n", "--log-dir", "L", "--db-dir", "D"])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("/tmp|True|True|L|D", r.stdout)
