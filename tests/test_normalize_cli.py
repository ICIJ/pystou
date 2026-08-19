import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import typer
from typer.testing import CliRunner

import normalize.main
from common import console
from common.errors import PystouError
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

    def test_dry_run_renders_bad_bytes_when_the_utf8_rule_is_not_selected(self):
        # A real terminal encodes what rich renders, so an unescaped
        # surrogateescape code point aborts the safe preview mode.
        make(self.dir, b"note_\x9f[x].txt")
        stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        console.configure(no_color=True, quiet=False, out_file=stream, err_file=self.err)

        result = self._invoke("--rule", "punct", "--dry-run")

        self.assertEqual(result.exit_code, 0, result.exception)
        stream.flush()
        self.assertIn("\\x9f", stream.buffer.getvalue().decode("utf-8"))

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

    def test_a_failing_entry_does_not_abort_the_rest(self):
        make(self.dir, b"a_\x9f.txt")
        make(self.dir, b"b_\x9f.txt")
        make(self.dir, b"c_\x9f.txt")
        real = normalize.main.apply_rename

        def flaky(old, new_name):
            if old.name.startswith("b_"):
                raise PermissionError(13, "Permission denied")
            return real(old, new_name)

        with mock.patch("normalize.main.apply_rename", flaky):
            result = self._invoke()

        self.assertEqual(result.exit_code, 0)
        self.assertTrue((Path(self.dir) / "a__.txt").exists())
        self.assertTrue((Path(self.dir) / "c__.txt").exists())
        self.assertTrue(os.path.lexists(os.fsencode(self.dir) + b"/b_\x9f.txt"))
        self.assertIn("1 failed", self.err.getvalue())
        _meta, entries = manifest.read(sorted(Path(self.state).glob("*.jsonl"))[0])
        self.assertEqual(len(entries), 2)

    def test_a_second_run_finds_nothing_left_to_do(self):
        bad_dir = Path(os.fsdecode(os.fsencode(self.dir) + b"/dir_\xed\xa0\xbd\xed\xb8\x80"))
        bad_dir.mkdir()
        make(bad_dir, b"a\x9f.txt", b"one")
        (Path(self.dir) / "Café. ").write_text("two")

        self.assertEqual(self._invoke("-r").exit_code, 0)
        after_first = _listing(self.dir)

        self.err.truncate(0)
        self.err.seek(0)
        self.assertEqual(self._invoke("-r").exit_code, 0)

        self.assertIn("No filenames need normalizing", self.err.getvalue())
        self.assertEqual(_listing(self.dir), after_first)


class TestRelativeDirectory(unittest.TestCase):
    """The manifest is replayed against Elasticsearch, so it must hold full paths."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.state = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        self.runner = CliRunner()

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def test_a_relative_directory_is_still_recorded_absolutely(self):
        sub = Path(self.dir) / "sub"
        sub.mkdir()
        make(sub, b"f_\x9f.txt")
        os.chdir(self.dir)

        result = self.runner.invoke(
            _app(), [".", "-r", "--log-dir", self.state, "--manifest-dir", self.state]
        )
        self.assertEqual(result.exit_code, 0)

        meta, entries = manifest.read(sorted(Path(self.state).glob("*.jsonl"))[0])
        self.assertTrue(os.path.isabs(meta["root"]), meta["root"])
        self.assertTrue(os.path.isabs(manifest.decode(meta["root_b64"])))
        self.assertTrue(entries)
        for entry in entries:
            with self.subTest(entry=entry["old"]):
                self.assertTrue(os.path.isabs(entry["old"]), entry["old"])
                self.assertTrue(os.path.isabs(entry["new"]), entry["new"])
                self.assertTrue(os.path.isabs(manifest.decode(entry["old_b64"])))
                self.assertTrue(os.path.isabs(manifest.decode(entry["new_b64"])))


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


class TestNoOpRun(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.state = tempfile.mkdtemp()
        self.runner = CliRunner()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def test_run_with_nothing_to_rename_writes_no_manifest(self):
        # Otherwise every clean run drops an orphan run id that --undo accepts.
        (Path(self.dir) / "fine.txt").write_text("x")
        result = self.runner.invoke(
            _app(), [self.dir, "--log-dir", self.state, "--manifest-dir", self.state]
        )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(list(Path(self.state).glob("*.jsonl")), [])


class TestNoManifest(unittest.TestCase):
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

    def test_renames_without_writing_a_manifest(self):
        make(self.dir, b"note_\x9f.txt")
        result = self.runner.invoke(_app(), [self.dir, "--log-dir", self.state, "--no-manifest"])
        self.assertEqual(result.exit_code, 0)
        self.assertTrue((Path(self.dir) / "note__.txt").exists())
        self.assertEqual(list(Path(self.state).glob("*.jsonl")), [])

    def test_warns_that_the_run_cannot_be_undone(self):
        # --undo replays a manifest, so skipping it forfeits the safety net.
        # That has to be said out loud, not left to --help.
        make(self.dir, b"note_\x9f.txt")
        self.runner.invoke(_app(), [self.dir, "--log-dir", self.state, "--no-manifest"])
        self.assertIn("cannot be undone", self.err.getvalue())

    def test_says_nothing_about_undo_when_no_rename_happened(self):
        (Path(self.dir) / "fine.txt").write_text("x")
        self.runner.invoke(_app(), [self.dir, "--log-dir", self.state, "--no-manifest"])
        self.assertNotIn("cannot be undone", self.err.getvalue())

    def test_rejects_no_manifest_combined_with_manifest_dir(self):
        result = self.runner.invoke(
            _app(),
            [self.dir, "--log-dir", self.state, "--manifest-dir", self.state, "--no-manifest"],
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIsInstance(result.exception, PystouError)
        self.assertIn("--no-manifest", str(result.exception))
