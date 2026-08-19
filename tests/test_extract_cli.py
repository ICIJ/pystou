import gzip
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import typer
from typer.testing import CliRunner

from common import trash
from extract.main import extract_command


def _app():
    app = typer.Typer()
    app.command()(extract_command)
    return app


def _split_runner():
    """A CliRunner with stdout/stderr kept separate across Click versions.

    Click <8.2 defaults to merging stderr into stdout (``mix_stderr=True``), which
    would let a ``print(..., file=sys.stderr)`` leak into ``result.stdout``; pass
    ``mix_stderr=False`` there. Click >=8.2 removed the parameter (streams are
    always separate), so fall back to the default constructor.
    """
    try:
        return CliRunner(mix_stderr=False)
    except TypeError:
        return CliRunner()


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
        self.assertTrue((Path(self.dir) / "a" / "inner.txt").is_file())
        self.assertTrue(self.zip_path.exists())  # default keep
        self.assertEqual(trash.list_runs(self.dir), [])

    def test_extract_stdout_is_clean(self):
        # extraction status ("Extracted ...") must go to stderr, not stdout
        r = _split_runner().invoke(
            _app(),
            [self.dir, "--action", "extract", "--log-dir", self.dir, "--db-dir", self.dir],
        )
        self.assertEqual(r.exit_code, 0)
        self.assertNotIn("Extracted", r.stdout)
        self.assertNotIn("\r", r.stdout)

    def test_remove_archives_quarantines(self):
        r = self.runner.invoke(_app(), self._common("--action", "extract", "--remove-archives"))
        self.assertEqual(r.exit_code, 0)
        self.assertTrue((Path(self.dir) / "a" / "inner.txt").is_file())
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
        self.assertFalse((Path(self.dir) / "a" / "inner.txt").exists())
        self.assertEqual(trash.list_runs(self.dir), [])

    def test_dry_run(self):
        r = self.runner.invoke(
            _app(), self._common("--action", "extract", "--remove-archives", "-n")
        )
        self.assertEqual(r.exit_code, 0)
        self.assertTrue(self.zip_path.exists())  # nothing removed
        self.assertEqual(trash.list_runs(self.dir), [])

    def test_tolerant_flag_threads_through(self):
        from unittest.mock import patch

        calls = {}

        def fake_extract(archive, tolerant=False):
            calls["tolerant"] = tolerant
            return True

        with patch("extract.main.extract_archive", side_effect=fake_extract):
            r = self.runner.invoke(_app(), self._common("--action", "extract", "--tolerant"))
        self.assertEqual(r.exit_code, 0)
        self.assertTrue(calls.get("tolerant"))

    def test_default_is_not_tolerant(self):
        from unittest.mock import patch

        calls = {}

        def fake_extract(archive, tolerant=False):
            calls["tolerant"] = tolerant
            return True

        with patch("extract.main.extract_archive", side_effect=fake_extract):
            r = self.runner.invoke(_app(), self._common("--action", "extract"))
        self.assertEqual(r.exit_code, 0)
        self.assertFalse(calls.get("tolerant"))


class TestExtractSurvivesBadArchive(unittest.TestCase):
    """A corrupt archive must not abort the run for the healthy ones."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.runner = _split_runner()
        bad = Path(self.dir) / "a.txt.gz"
        with gzip.open(bad, "wb") as f:
            f.write(os.urandom(200_000))
        payload = bad.read_bytes()
        bad.write_bytes(payload[: len(payload) // 2])
        with zipfile.ZipFile(Path(self.dir) / "z_good.zip", "w") as z:
            z.writestr("inner.txt", "hi")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_healthy_archive_is_still_extracted(self):
        r = self.runner.invoke(
            _app(),
            [self.dir, "--action", "extract", "--log-dir", self.dir, "--db-dir", self.dir],
        )

        self.assertEqual(r.exit_code, 0)
        self.assertTrue((Path(self.dir) / "z_good" / "inner.txt").is_file())
        self.assertFalse((Path(self.dir) / "a.txt").exists())


class TestNestedExtraction(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.runner = _split_runner()
        for name in ("a.zip", "b.zip"):
            with zipfile.ZipFile(Path(self.dir) / name, "w") as z:
                z.writestr("inner.txt", "hi")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _invoke(self, *extra):
        return self.runner.invoke(
            _app(),
            [self.dir, "--nested", "--log-dir", self.dir, "--db-dir", self.dir, *extra],
        )

    def test_each_archive_is_extracted_once(self):
        calls = []

        def fake_extract(archive, tolerant=False):
            calls.append(archive)
            return True

        with patch("extract.main.extract_archive", side_effect=fake_extract):
            r = self._invoke("--action", "extract", "--max-depth", "4")

        self.assertEqual(r.exit_code, 0)
        self.assertEqual(sorted(p.name for p in calls), ["a.zip", "b.zip"])

    def test_nested_pass_honours_a_skipped_archive(self):
        calls = []

        def fake_extract(archive, tolerant=False):
            calls.append(archive)
            return True

        def fake_choice(prompt, choices, default=None):
            return "extract" if "a.zip" in prompt else "skip"

        with (
            patch("extract.main.extract_archive", side_effect=fake_extract),
            patch("common.console.prompt_choice", side_effect=fake_choice),
        ):
            r = self._invoke("--max-depth", "4")

        self.assertEqual(r.exit_code, 0)
        self.assertEqual([p.name for p in calls], ["a.zip"])


class TestParallelNestedDepth(unittest.TestCase):
    """The parallel path must honour --max-depth like the sequential one."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.runner = _split_runner()
        inner = Path(self.dir) / "src" / "inner.zip"
        inner.parent.mkdir()
        with zipfile.ZipFile(inner, "w") as z:
            z.writestr("deep.txt", "hi")
        with zipfile.ZipFile(Path(self.dir) / "outer.zip", "w") as z:
            z.write(inner, arcname="inner.zip")
        shutil.rmtree(inner.parent)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _invoke(self, max_depth):
        return self.runner.invoke(
            _app(),
            [
                self.dir,
                "--action",
                "extract",
                "--nested",
                "-p",
                "4",
                "--max-depth",
                str(max_depth),
                "--log-dir",
                self.dir,
                "--db-dir",
                self.dir,
            ],
        )

    def test_max_depth_zero_does_not_recurse(self):
        r = self._invoke(0)

        self.assertEqual(r.exit_code, 0)
        self.assertTrue((Path(self.dir) / "outer" / "inner.zip").is_file())
        self.assertFalse((Path(self.dir) / "outer" / "inner").exists())

    def test_max_depth_one_recurses_once(self):
        r = self._invoke(1)

        self.assertEqual(r.exit_code, 0)
        self.assertTrue((Path(self.dir) / "outer" / "inner" / "deep.txt").is_file())
