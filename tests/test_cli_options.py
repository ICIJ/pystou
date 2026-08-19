import shutil
import tempfile
import unittest

import typer
from typer.testing import CliRunner

from cleanup.main import cleanup_command
from common.cli import DbDirOpt, DirectoryArg, DryRunOpt, LogDirOpt, RecursiveOpt
from empty.main import empty_command
from identify.main import identify_command
from stats.main import stats_command


class TestSharedOptions(unittest.TestCase):
    def test_options_parse(self):
        app = typer.Typer()

        @app.command()
        def cmd(
            directory: DirectoryArg = ".",
            recursive: RecursiveOpt = False,
            dry_run: DryRunOpt = False,
            log_dir: LogDirOpt = None,
            db_dir: DbDirOpt = None,
        ):
            typer.echo(f"{directory}|{recursive}|{dry_run}|{log_dir}|{db_dir}")

        r = CliRunner().invoke(app, ["/tmp", "-r", "-n", "--log-dir", "L", "--db-dir", "D"])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("/tmp|True|True|L|D", r.stdout)

    def test_omitted_directories_stay_unset_for_the_callee_to_resolve(self):
        app = typer.Typer()

        @app.command()
        def cmd(log_dir: LogDirOpt = None, db_dir: DbDirOpt = None):
            typer.echo(f"{log_dir}|{db_dir}")

        r = CliRunner().invoke(app, [])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("None|None", r.stdout)


class TestDbDirNotOfferedWithoutAnIndex(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_commands_without_an_index_reject_db_dir(self):
        """Commands that never open the database must not advertise --db-dir."""
        for command in (cleanup_command, empty_command, identify_command, stats_command):
            with self.subTest(command=command.__name__):
                app = typer.Typer()
                app.command()(command)
                r = CliRunner().invoke(app, [self.dir, "--log-dir", self.dir, "--db-dir", self.dir])
                self.assertNotEqual(r.exit_code, 0)
