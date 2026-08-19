import io
import shutil
import tempfile
import unittest
from pathlib import Path

import typer
from typer.testing import CliRunner

from common import console
from empty.main import empty_command


def _app():
    app = typer.Typer()
    app.command()(empty_command)
    return app


class TestEmptyCommand(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.runner = CliRunner()
        self.out = io.StringIO()
        self.err = io.StringIO()
        console.configure(no_color=True, quiet=False, out_file=self.out, err_file=self.err)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        console.configure()

    def _args(self, *extra):
        return [self.dir, "--log-dir", self.dir, *extra]

    def _invoke(self, *extra):
        return self.runner.invoke(_app(), self._args(*extra))

    def test_removes_empty_dir(self):
        """Empty directory is removed when no flags given (recursive)."""
        (Path(self.dir) / "empty_one").mkdir()
        r = self._invoke("-r")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertFalse((Path(self.dir) / "empty_one").exists())

    def test_list_only_keeps(self):
        """--list-only reports but does not remove the empty directory."""
        (Path(self.dir) / "listed_empty").mkdir()
        r = self._invoke("--list-only")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertTrue((Path(self.dir) / "listed_empty").exists())

    def test_dry_run_keeps(self):
        """-n (dry-run) reports but does not remove the empty directory."""
        (Path(self.dir) / "dry_empty").mkdir()
        r = self._invoke("-n")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertTrue((Path(self.dir) / "dry_empty").exists())

    def test_excludes_trash(self):
        """Dirs under .pystou-trash are never touched or reported."""
        # Empty dir inside the trash — must be ignored
        (Path(self.dir) / ".pystou-trash" / "r" / "0").mkdir(parents=True)
        # Real empty dir alongside the trash — must be removed
        (Path(self.dir) / "real_empty").mkdir()

        r = self._invoke("-r", "--include-hidden")
        self.assertEqual(r.exit_code, 0, r.output)

        # real_empty should be gone
        self.assertFalse((Path(self.dir) / "real_empty").exists())
        # trash subtree must be untouched
        self.assertTrue((Path(self.dir) / ".pystou-trash" / "r" / "0").exists())
        # nothing under .pystou-trash should appear in err output
        self.assertNotIn(".pystou-trash", self.err.getvalue())

    def test_no_empty_dirs(self):
        """A directory that contains only a file produces the 'none found' message."""
        (Path(self.dir) / "keepme.txt").write_text("data")
        r = self._invoke()
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("No empty directories found.", self.err.getvalue())


if __name__ == "__main__":
    unittest.main()
