import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import typer
from typer.testing import CliRunner

from common import trash
from extract.main import extract_command


def _app():
    app = typer.Typer()
    app.command()(extract_command)
    return app


class TestExtractCommand(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.runner = CliRunner()
        self.zip_path = Path(self.dir) / "a.zip"
        with zipfile.ZipFile(self.zip_path, "w") as z:
            z.writestr("inner.txt", "hi")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _common(self, *extra):
        return [self.dir, "--log-dir", self.dir, "--db-dir", self.dir, *extra]

    def test_extract_only_keeps_archive_by_default(self):
        r = self.runner.invoke(_app(), self._common("--action", "extract"))
        self.assertEqual(r.exit_code, 0)
        self.assertTrue((Path(self.dir) / "inner.txt").is_file())
        self.assertTrue(self.zip_path.exists())  # default keep
        self.assertEqual(trash.list_runs(self.dir), [])

    def test_remove_archives_quarantines(self):
        r = self.runner.invoke(_app(), self._common("--action", "extract", "--remove-archives"))
        self.assertEqual(r.exit_code, 0)
        self.assertTrue((Path(self.dir) / "inner.txt").is_file())
        self.assertFalse(self.zip_path.exists())
        self.assertEqual(len(trash.list_runs(self.dir)), 1)

    def test_remove_archives_hard_delete(self):
        r = self.runner.invoke(
            _app(),
            self._common("--action", "extract", "--remove-archives", "--hard-delete"),
        )
        self.assertEqual(r.exit_code, 0)
        self.assertFalse(self.zip_path.exists())
        self.assertEqual(trash.list_runs(self.dir), [])

    def test_action_skip(self):
        r = self.runner.invoke(_app(), self._common("--action", "skip"))
        self.assertEqual(r.exit_code, 0)
        self.assertTrue(self.zip_path.exists())
        self.assertFalse((Path(self.dir) / "inner.txt").exists())
        self.assertEqual(trash.list_runs(self.dir), [])

    def test_dry_run(self):
        r = self.runner.invoke(
            _app(), self._common("--action", "extract", "--remove-archives", "-n")
        )
        self.assertEqual(r.exit_code, 0)
        self.assertTrue(self.zip_path.exists())  # nothing removed
        self.assertEqual(trash.list_runs(self.dir), [])
