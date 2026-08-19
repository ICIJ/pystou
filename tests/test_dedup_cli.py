import shutil
import tempfile
import unittest
from pathlib import Path

import typer
from typer.testing import CliRunner

from common import trash
from common.fs_walker import collect_directories
from common.indexer import close_database, index_db_path, initialize_database
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


class TestDedupScopedToTarget(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.runner = CliRunner()
        self.elsewhere = Path(self.dir) / "elsewhere"
        (self.elsewhere / "data").mkdir(parents=True)
        (self.elsewhere / "data (1)").mkdir()
        self.target = Path(self.dir) / "target"
        self.target.mkdir()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_stale_index_outside_target_is_left_alone(self):
        conn = initialize_database(index_db_path(self.dir, str(self.target)))
        collect_directories(conn, str(self.elsewhere), recursive=True)
        close_database(conn)
        r = self.runner.invoke(
            _app(),
            [
                str(self.target),
                "-r",
                "--action",
                "delete",
                "--hard-delete",
                "--db-dir",
                self.dir,
                "--log-dir",
                self.dir,
            ],
            input="y\n",
        )
        self.assertEqual(r.exit_code, 0)
        self.assertTrue((self.elsewhere / "data (1)").exists())
