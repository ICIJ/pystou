import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import typer
from typer.testing import CliRunner

from common import console
from normalize import manifest
from normalize.main import normalize_command


def _app():
    app = typer.Typer()
    app.command()(normalize_command)
    return app


def make(root, raw: bytes, content: bytes = b"x") -> Path:
    path = Path(os.fsdecode(os.fsencode(str(root)) + b"/" + raw))
    path.write_bytes(content)
    return path


class TestNormalizeCLI(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.state = tempfile.mkdtemp()
        self.runner = CliRunner()
        self.out = io.StringIO()
        self.err = io.StringIO()
        console.configure(no_color=True, quiet=False, out_file=self.out, err_file=self.err)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)
        console.configure()

    def _invoke(self, *args):
        return self.runner.invoke(
            _app(),
            [self.dir, "--log-dir", self.state, "--manifest-dir", self.state, *args],
        )

    def test_dry_run_changes_nothing_and_writes_no_manifest(self):
        make(self.dir, b"note_\x9f.txt")
        result = self._invoke("--dry-run")
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(os.path.lexists(os.fsencode(self.dir) + b"/note_\x9f.txt"))
        self.assertEqual(list(Path(self.state).glob("*.jsonl")), [])

    def test_renames_and_writes_a_manifest(self):
        make(self.dir, b"note_\x9f.txt")
        result = self._invoke()
        self.assertEqual(result.exit_code, 0)
        self.assertTrue((Path(self.dir) / "note__.txt").exists())
        manifests = list(Path(self.state).glob("*.jsonl"))
        self.assertEqual(len(manifests), 1)
        meta, entries = manifest.read(manifests[0])
        self.assertEqual(meta["root"], self.dir)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["mode"], "stripped")

    def test_rule_selection_leaves_other_problems_alone(self):
        nfd = "Café.pdf"
        (Path(self.dir) / nfd).write_text("x")
        make(self.dir, b"note_\x9f.txt")
        result = self._invoke("--rule", "utf8")
        self.assertEqual(result.exit_code, 0)
        # Still NFD on disk: --rule utf8 must not have composed it.
        self.assertIn(nfd, [p.name for p in Path(self.dir).iterdir()])
        self.assertTrue((Path(self.dir) / "note__.txt").exists())

    def test_clean_tree_reports_nothing_to_do(self):
        (Path(self.dir) / "fine.txt").write_text("x")
        result = self._invoke()
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No filenames need normalizing", self.err.getvalue())

    def test_non_recursive_leaves_subdirectory_contents_alone(self):
        sub = Path(self.dir) / "sub"
        sub.mkdir()
        make(sub, b"deep_\x9f.txt")
        result = self._invoke()
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(os.path.lexists(os.fsencode(str(sub)) + b"/deep_\x9f.txt"))


class TestRoundTripInvariant(unittest.TestCase):
    """The invariant the Datashare update depends on: undo is byte-exact."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.state = tempfile.mkdtemp()
        self.runner = CliRunner()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def test_normalize_then_undo_restores_every_byte(self):
        bad_dir = Path(os.fsdecode(os.fsencode(self.dir) + b"/dir_\xed\xa0\xbd\xed\xb8\x80"))
        bad_dir.mkdir()
        make(bad_dir, b"a\x9f.txt", b"one")
        make(bad_dir, b"a\x98.txt", b"two")
        (Path(self.dir) / "Café. ").write_text("three")
        before = _listing(self.dir)

        result = self.runner.invoke(
            _app(),
            [self.dir, "-r", "--log-dir", self.state, "--manifest-dir", self.state],
        )
        self.assertEqual(result.exit_code, 0)

        for path in _listing(self.dir):
            with self.subTest(path=path):
                path.decode("utf-8")  # raises if the tree is still not S3-safe

        run_id = sorted(Path(self.state).glob("*.jsonl"))[0].stem
        undo = self.runner.invoke(
            _app(),
            [self.dir, "--undo", run_id, "--log-dir", self.state, "--manifest-dir", self.state],
        )
        self.assertEqual(undo.exit_code, 0)
        self.assertEqual(_listing(self.dir), before)


def _listing(root) -> list[bytes]:
    found = []
    for current, dirs, files in os.walk(os.fsencode(str(root))):
        for name in sorted(dirs) + sorted(files):
            found.append(os.path.join(current, name))
    return sorted(found)
