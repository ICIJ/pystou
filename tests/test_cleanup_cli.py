import shutil
import tempfile
import unittest
from pathlib import Path

import typer
from typer.testing import CliRunner

from cleanup.main import cleanup_command
from common import trash


def _app():
    app = typer.Typer()
    app.command()(cleanup_command)
    return app


def _split_runner():
    """CliRunner with stdout/stderr kept separate across Click versions.

    Click <8.2 merges stderr into stdout by default; pass mix_stderr=False there.
    Click >=8.2 removed the parameter (always separate), so fall back.
    """
    try:
        return CliRunner(mix_stderr=False)
    except TypeError:
        return CliRunner()


class TestCleanupCommand(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.runner = CliRunner()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_quarantines_by_default(self):
        (Path(self.dir) / ".DS_Store").write_text("junk")
        r = self.runner.invoke(_app(), [self.dir, "--log-dir", self.dir])
        self.assertEqual(r.exit_code, 0)
        self.assertFalse((Path(self.dir) / ".DS_Store").exists())
        self.assertEqual(len(trash.list_runs(self.dir)), 1)

    def test_hard_delete(self):
        (Path(self.dir) / ".DS_Store").write_text("junk")
        r = self.runner.invoke(_app(), [self.dir, "--hard-delete", "--log-dir", self.dir])
        self.assertEqual(r.exit_code, 0)
        self.assertFalse((Path(self.dir) / ".DS_Store").exists())
        self.assertEqual(trash.list_runs(self.dir), [])

    def test_list_only_does_not_remove(self):
        (Path(self.dir) / ".DS_Store").write_text("junk")
        r = self.runner.invoke(_app(), [self.dir, "--list-only", "--log-dir", self.dir])
        self.assertEqual(r.exit_code, 0)
        self.assertTrue((Path(self.dir) / ".DS_Store").exists())

    def test_dry_run_no_op(self):
        (Path(self.dir) / ".DS_Store").write_text("junk")
        r = self.runner.invoke(_app(), [self.dir, "-n", "--log-dir", self.dir])
        self.assertEqual(r.exit_code, 0)
        self.assertTrue((Path(self.dir) / ".DS_Store").exists())

    def test_dry_run_stdout_clean(self):
        (Path(self.dir) / ".DS_Store").write_text("x")
        r = _split_runner().invoke(_app(), [self.dir, "-n", "--log-dir", self.dir])
        self.assertEqual(r.exit_code, 0)
        self.assertNotIn("\r", r.stdout)

    def test_no_junk(self):
        r = self.runner.invoke(_app(), [self.dir, "--log-dir", self.dir])
        self.assertEqual(r.exit_code, 0)

    def test_include_removes_matching_directory(self):
        (Path(self.dir) / "node_modules").mkdir()
        r = self.runner.invoke(
            _app(),
            [self.dir, "-r", "--include", "node_modules", "--log-dir", self.dir],
        )
        self.assertEqual(r.exit_code, 0)
        self.assertFalse((Path(self.dir) / "node_modules").exists())
