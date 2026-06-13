import shutil
import tempfile
import unittest
from pathlib import Path

import typer
from typer.testing import CliRunner

from common import trash
from dedup_folders.main import dedup_command


def _app():
    app = typer.Typer()
    app.command()(dedup_command)
    return app


class TestDedupCommand(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.runner = CliRunner()
        base = Path(self.dir) / "data"
        base.mkdir()
        (base / "f.txt").write_text("x")
        dup = Path(self.dir) / "data (1)"
        dup.mkdir()
        (dup / "f.txt").write_text("x")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _common(self, *extra):
        return [self.dir, "-r", "--log-dir", self.dir, "--db-dir", self.dir, *extra]

    def test_action_delete_quarantines(self):
        r = self.runner.invoke(_app(), self._common("--action", "delete"))
        self.assertEqual(r.exit_code, 0)
        self.assertFalse((Path(self.dir) / "data (1)").exists())
        self.assertEqual(len(trash.list_runs(self.dir)), 1)

    def test_action_skip_keeps_all(self):
        r = self.runner.invoke(_app(), self._common("--action", "skip"))
        self.assertEqual(r.exit_code, 0)
        self.assertTrue((Path(self.dir) / "data (1)").exists())
        self.assertEqual(trash.list_runs(self.dir), [])

    def test_action_delete_hard(self):
        r = self.runner.invoke(_app(), self._common("--action", "delete", "--hard-delete"))
        self.assertEqual(r.exit_code, 0)
        self.assertFalse((Path(self.dir) / "data (1)").exists())
        self.assertEqual(trash.list_runs(self.dir), [])

    def test_prompt_when_no_action(self):
        # no --action -> interactive prompt; feed "delete"
        r = self.runner.invoke(_app(), self._common(), input="delete\n")
        self.assertEqual(r.exit_code, 0)
        self.assertFalse((Path(self.dir) / "data (1)").exists())

    def test_action_merge_quarantines_emptied_dup(self):
        # give the dup a non-conflicting file; remove the conflicting one for a clean merge
        (Path(self.dir) / "data (1)" / "f.txt").unlink()
        (Path(self.dir) / "data (1)" / "g.txt").write_text("y")
        r = self.runner.invoke(_app(), self._common("--action", "merge"))
        self.assertEqual(r.exit_code, 0)
        self.assertTrue((Path(self.dir) / "data" / "g.txt").is_file())  # merged into base
        self.assertFalse((Path(self.dir) / "data (1)").exists())  # emptied dup quarantined
        self.assertEqual(len(trash.list_runs(self.dir)), 1)

    def test_dry_run_no_op(self):
        r = self.runner.invoke(_app(), self._common("--action", "delete", "-n"))
        self.assertEqual(r.exit_code, 0)
        self.assertTrue((Path(self.dir) / "data (1)").exists())  # nothing removed
        self.assertEqual(trash.list_runs(self.dir), [])
