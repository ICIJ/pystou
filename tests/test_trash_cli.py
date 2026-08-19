# tests/test_trash_cli.py
"""Typer CLI tests for the trash sub-app (list / purge)."""

import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from common import console, trash
from trash.main import trash_app


class TestTrashCli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.runner = CliRunner()
        self.out = io.StringIO()
        self.err = io.StringIO()
        console.configure(no_color=True, quiet=False, out_file=self.out, err_file=self.err)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        console.configure()

    def _args(self, sub, *extra):
        return [sub, self.dir, "--log-dir", self.dir, *extra]

    # ------------------------------------------------------------------
    # test_list_empty
    # Fresh directory has no trash → the searched trash root and the
    # --trash-dir hint on stderr; exit 0.
    # ------------------------------------------------------------------
    def test_list_empty(self):
        r = self.runner.invoke(trash_app, self._args("list"))
        self.assertEqual(r.exit_code, 0, r.output)
        # console.status writes to the configured err file
        err = self.err.getvalue()
        self.assertIn(str(Path(self.dir) / ".pystou-trash"), err)
        self.assertIn("--trash-dir", err)

    # ------------------------------------------------------------------
    # test_list_shows_run
    # After quarantining a file, list exits 0 and the operation name
    # appears somewhere (table rendered to the configured out file).
    # ------------------------------------------------------------------
    def test_list_shows_run(self):
        victim = Path(self.dir) / "victim.txt"
        victim.write_text("data")
        trash.quarantine([victim], self.dir, operation="cleanup", command="c")

        r = self.runner.invoke(trash_app, self._args("list"))
        self.assertEqual(r.exit_code, 0, r.output)
        out = self.out.getvalue()
        self.assertIn("cleanup", out)

    # ------------------------------------------------------------------
    # test_list_json_pure
    # --json must emit parseable JSON to stdout (via CliRunner capture),
    # be a list containing the run, and contain NO ANSI escape sequences.
    # KEY TEST: console.print_json writes to sys.stdout; CliRunner
    # patches sys.stdout, so the write lands in r.output.
    # ------------------------------------------------------------------
    def test_list_json_pure(self):
        victim = Path(self.dir) / "file.txt"
        victim.write_text("hello")
        trash.quarantine([victim], self.dir, operation="cleanup", command="c")

        r = self.runner.invoke(trash_app, self._args("list", "--json"))
        self.assertEqual(r.exit_code, 0, r.output)
        raw = r.output  # CliRunner captures sys.stdout
        # Must parse as valid JSON
        parsed = json.loads(raw)
        # Must be a non-empty list
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), 1)
        run_obj = parsed[0]
        # Key fields present
        self.assertIn("run_id", run_obj)
        self.assertIn("operation", run_obj)
        self.assertIn("items", run_obj)
        self.assertIn("reclaimable_bytes", run_obj)
        self.assertEqual(run_obj["operation"], "cleanup")
        self.assertEqual(run_obj["items"], 1)
        # No ANSI escape sequences
        self.assertNotIn("\x1b[", raw, "JSON output must not contain ANSI escape codes")

    # ------------------------------------------------------------------
    # test_purge_all_empties
    # After quarantining a file and running purge --all, list_runs is [].
    # ------------------------------------------------------------------
    def test_purge_all_empties(self):
        victim = Path(self.dir) / "g.txt"
        victim.write_text("x")
        trash.quarantine([victim], self.dir, operation="cleanup", command="c")
        self.assertEqual(len(trash.list_runs(self.dir)), 1)

        r = self.runner.invoke(trash_app, self._args("purge", "--all"))
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertEqual(trash.list_runs(self.dir), [])


if __name__ == "__main__":
    unittest.main()
