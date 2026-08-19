import io
import shutil
import tempfile
import unittest
from pathlib import Path

import typer
from typer.testing import CliRunner

from common import console, trash
from restore.main import restore_command


def _app():
    app = typer.Typer()
    app.command()(restore_command)
    return app


class TestRestoreCommand(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.runner = CliRunner()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_restore_all_round_trip(self):
        victim = Path(self.dir) / "f.txt"
        victim.write_text("data")
        trash.quarantine([victim], self.dir, operation="cleanup", command="c")
        self.assertFalse(victim.exists())
        r = self.runner.invoke(
            _app(), [self.dir, "--all", "--log-dir", self.dir, "--db-dir", self.dir]
        )
        self.assertEqual(r.exit_code, 0)
        self.assertTrue(victim.is_file())

    def test_no_flags_guidance(self):
        r = self.runner.invoke(_app(), [self.dir, "--log-dir", self.dir, "--db-dir", self.dir])
        # guidance printed to stderr; exit 0 is the key assertion
        self.assertEqual(r.exit_code, 0)

    def test_restore_by_run(self):
        victim = Path(self.dir) / "g.txt"
        victim.write_text("hello")
        run_id = trash.quarantine([victim], self.dir, operation="cleanup", command="c")
        self.assertFalse(victim.exists())
        r = self.runner.invoke(
            _app(),
            [self.dir, "--run", run_id, "--log-dir", self.dir, "--db-dir", self.dir],
        )
        self.assertEqual(r.exit_code, 0)
        self.assertTrue(victim.is_file())

    def test_restore_by_path_only(self):
        victim = Path(self.dir) / "h.txt"
        victim.write_text("hi")
        trash.quarantine([victim], self.dir, operation="cleanup", command="c")
        r = self.runner.invoke(
            _app(),
            [self.dir, "--path", str(victim), "--log-dir", self.dir, "--db-dir", self.dir],
        )
        self.assertEqual(r.exit_code, 0)
        self.assertTrue(victim.is_file())

    def test_nothing_to_restore_names_the_trash_root(self):
        out = io.StringIO()
        err = io.StringIO()
        console.configure(no_color=True, out_file=out, err_file=err)
        self.addCleanup(console.configure)
        r = self.runner.invoke(
            _app(), [self.dir, "--all", "--log-dir", self.dir, "--db-dir", self.dir]
        )
        self.assertEqual(r.exit_code, 0)
        self.assertIn(str(Path(self.dir) / ".pystou-trash"), err.getvalue())
        self.assertIn("--trash-dir", err.getvalue())


if __name__ == "__main__":
    unittest.main()
