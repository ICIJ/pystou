import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import typer
from typer.testing import CliRunner

from common import console
from stats.main import stats_command


def _app():
    app = typer.Typer()
    app.command()(stats_command)
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


class TestStatsCommand(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.runner = CliRunner()
        self.out = io.StringIO()
        self.err = io.StringIO()
        console.configure(no_color=True, quiet=False, out_file=self.out, err_file=self.err)

        # Create a couple of test files so stats are non-trivial
        (Path(self.dir) / "alpha.txt").write_bytes(b"a" * 100)
        (Path(self.dir) / "beta.pdf").write_bytes(b"b" * 200)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        console.configure()

    def _args(self, *extra):
        return [self.dir, "--log-dir", self.dir, *extra]

    def _invoke(self, *extra):
        return self.runner.invoke(_app(), self._args(*extra))

    # ------------------------------------------------------------------
    # test_human_summary
    # Plain run (no --json) should exit 0 and print the summary table.
    # console.print_table writes to the configured _out buffer, so we
    # read self.out.getvalue() for the table content.
    # ------------------------------------------------------------------
    def test_human_summary(self):
        r = self._invoke("-r")
        self.assertEqual(r.exit_code, 0, r.output)
        out = self.out.getvalue()
        self.assertIn("Total files", out)

    # ------------------------------------------------------------------
    # test_json_is_pure
    # --json must emit parseable JSON with no ANSI escape sequences.
    # console.print_json writes to `file or sys.stdout`; since no file
    # arg is passed, it uses sys.stdout.  CliRunner patches sys.stdout
    # during invoke, so r.output captures the write.
    # ------------------------------------------------------------------
    def test_json_is_pure(self):
        r = self._invoke("--json")
        self.assertEqual(r.exit_code, 0, r.output)
        raw = r.output  # CliRunner captures sys.stdout writes
        # Must parse as valid JSON
        parsed = json.loads(raw)
        self.assertIn("summary", parsed)
        self.assertIn("by_extension", parsed)
        self.assertIn("largest_files", parsed)
        self.assertIn("empty_directories", parsed)
        # Must not contain any ANSI escape sequences
        self.assertNotIn("\x1b[", raw, "JSON output must not contain ANSI escape codes")

    # ------------------------------------------------------------------
    # test_by_size
    # --by-size should exit 0 (at minimum, no crash).
    # ------------------------------------------------------------------
    def test_by_size(self):
        r = self._invoke("--by-size")
        self.assertEqual(r.exit_code, 0, r.output)

    # ------------------------------------------------------------------
    # test_by_extension
    # --by-extension should exit 0 and print the extension table.
    # The extension table goes to console._out (configured to self.out).
    # ------------------------------------------------------------------
    def test_by_extension(self):
        r = self._invoke("--by-extension")
        self.assertEqual(r.exit_code, 0, r.output)
        out = self.out.getvalue()
        # The extension table should show at least one extension
        self.assertIn(".txt", out)

    # ------------------------------------------------------------------
    # test_json_pure_on_large_tree
    # >1000 dirs would previously trigger a "Scanned N...\r" print to
    # stdout BEFORE the JSON, breaking json.loads(stdout).  We point the
    # console at the real streams (CliRunner patches sys.stdout) so any
    # leaked chrome would show up in r.stdout alongside the JSON.
    # ------------------------------------------------------------------
    def test_json_pure_on_large_tree(self):
        console.configure(no_color=True, quiet=False)
        big = Path(self.dir) / "big"
        for i in range(1100):
            (big / f"d{i}").mkdir(parents=True)
        runner = _split_runner()  # keep stdout/stderr separate on all Click versions
        r = runner.invoke(
            _app(),
            [str(big), "-r", "--json", "--log-dir", self.dir],
        )
        self.assertEqual(r.exit_code, 0, r.output)
        json.loads(r.stdout)  # must parse — no progress line leaked
        self.assertNotIn("\r", r.stdout)
        self.assertNotIn("\x1b[", r.stdout)

    # ------------------------------------------------------------------
    # test_stdout_has_no_chrome
    # A human (non-json) run produces a table on stdout but must not leak
    # any progress/scan chrome ("Scanned ...", "\r") onto stdout.  With
    # mix_stderr=False, r.stdout holds only the primary data stream.
    # ------------------------------------------------------------------
    def test_stdout_has_no_chrome(self):
        console.configure(no_color=True, quiet=False)
        big = Path(self.dir) / "big"
        for i in range(1100):
            (big / f"d{i}").mkdir(parents=True)
        runner = _split_runner()  # keep stdout/stderr separate on all Click versions
        r = runner.invoke(
            _app(),
            [str(big), "-r", "--log-dir", self.dir],
        )
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertNotIn("\r", r.stdout)
        self.assertNotIn("Scanned", r.stdout)


if __name__ == "__main__":
    unittest.main()
