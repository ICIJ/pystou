# tests/test_utils_extract.py
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

import common.utils as utils


class TestExtractArchiveSafety(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_traversal_zip_is_not_extracted_outside(self):
        zip_path = Path(self.test_dir) / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../escaped.txt", "pwned")
        result = utils.extract_archive(zip_path)
        self.assertFalse(result)
        self.assertFalse((Path(self.test_dir).parent / "escaped.txt").exists())

    def test_zst_decompress_does_not_clobber_existing_output(self):
        zstd = self._import_zstd_or_skip()
        # Create plain.txt.zst whose decompressed target plain.txt already exists.
        data = b"new-content"
        src = Path(self.test_dir) / "plain.txt.zst"
        with open(src, "wb") as f:
            f.write(zstd.ZstdCompressor().compress(data))
        existing = Path(self.test_dir) / "plain.txt"
        existing.write_text("original")
        self.assertTrue(utils.extract_archive(src))
        # Original must be preserved; decompressed output went to a unique path.
        self.assertEqual(existing.read_text(), "original")

    def test_gz_decompress_does_not_clobber_existing_output(self):
        import gzip

        src = Path(self.test_dir) / "plain.txt.gz"
        with gzip.open(src, "wb") as f:
            f.write(b"new-content")
        existing = Path(self.test_dir) / "plain.txt"
        existing.write_text("original")
        self.assertTrue(utils.extract_archive(src))
        # Original preserved; decompressed output went to a unique path.
        self.assertEqual(existing.read_text(), "original")
        self.assertTrue((Path(self.test_dir) / "plain.txt (1)").exists())

    def test_failed_gz_extraction_cleans_up_reserved_file(self):
        bad = Path(self.test_dir) / "corrupt.gz"
        bad.write_bytes(b"this is not valid gzip data")  # gzip read will raise

        result = utils.extract_compressed_file(bad)

        self.assertFalse(result)
        # The reserved output file must not be left behind on failure.
        self.assertFalse((Path(self.test_dir) / "corrupt").exists())

    def _import_zstd_or_skip(self):
        try:
            import zstandard as zstd

            return zstd
        except ImportError:
            self.skipTest("zstandard module not installed")


class TestZstdCommandPath(unittest.TestCase):
    """Exercises the zstd CLI extraction path without the zstd binary."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_tar_zst_command_path_reads_what_it_wrote(self):
        from unittest.mock import patch

        # Build a real tar that zstd would have produced on decompression.
        inner = Path(self.test_dir) / "payload_unique.txt"
        inner.write_text("hello")
        # The archive the user is "extracting".
        archive = Path(self.test_dir) / "bundle.tar.zst"
        archive.write_bytes(b"placeholder-compressed-bytes")

        # The function computes output_path = unique_path(archive.with_suffix("")),
        # i.e. .../bundle.tar. Our fake zstd writes the real tar there.
        expected_output = archive.with_suffix("")  # bundle.tar

        def fake_run(cmd, *args, **kwargs):
            # cmd == ["zstd", "-d", str(archive), "-o", str(expected_output)]
            out_path = Path(cmd[cmd.index("-o") + 1])
            with tarfile.open(out_path, "w") as tf:
                tf.add(inner, arcname="payload_unique.txt")

            class _R:
                returncode = 0

            return _R()

        with patch.object(utils.subprocess, "run", side_effect=fake_run):
            result = utils._extract_zst_with_command(archive)

        self.assertTrue(result)
        # The tar's contents were extracted next to the archive.
        self.assertTrue((Path(self.test_dir) / "payload_unique.txt").exists())
        # The temporary decompressed tar was cleaned up.
        self.assertFalse(expected_output.exists())

    def test_keyboardinterrupt_cleans_up_reserved_output(self):
        from unittest.mock import patch

        archive = Path(self.test_dir) / "blob.zst"
        archive.write_bytes(b"placeholder-zst-bytes")
        reserved = archive.with_suffix("")  # blob

        def boom(cmd, *args, **kwargs):
            raise KeyboardInterrupt()

        with (
            patch.object(utils.subprocess, "run", side_effect=boom),
            self.assertRaises(KeyboardInterrupt),
        ):
            utils._extract_zst_with_command(archive)

        # The reserved placeholder must not be left behind on abrupt exit.
        self.assertFalse(reserved.exists())


class TestCollapseRedundantRoot(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_collapses_single_nested_root(self):
        out = Path(self.test_dir) / "555555"
        inner = out / "555555"
        (inner / "sub").mkdir(parents=True)
        (inner / "a.txt").write_text("hi")

        utils._collapse_redundant_root(out)

        self.assertTrue((out / "a.txt").exists())
        self.assertTrue((out / "sub").is_dir())
        self.assertFalse((out / "555555").exists())

    def test_noop_on_multiple_entries(self):
        out = Path(self.test_dir) / "out"
        (out / "one").mkdir(parents=True)
        (out / "two").mkdir()

        utils._collapse_redundant_root(out)

        self.assertTrue((out / "one").is_dir())
        self.assertTrue((out / "two").is_dir())

    def test_noop_on_single_file_entry(self):
        out = Path(self.test_dir) / "out"
        out.mkdir()
        (out / "file.txt").write_text("x")

        utils._collapse_redundant_root(out)

        self.assertTrue((out / "file.txt").exists())

    def test_noop_on_empty_dir(self):
        out = Path(self.test_dir) / "out"
        out.mkdir()

        utils._collapse_redundant_root(out)

        self.assertTrue(out.is_dir())
        self.assertEqual(list(out.iterdir()), [])

    def test_noop_on_single_symlink_to_dir(self):
        out = Path(self.test_dir) / "out"
        out.mkdir()
        real_target = Path(self.test_dir) / "elsewhere"
        (real_target / "mail").mkdir(parents=True)
        link = out / "linked"
        link.symlink_to(real_target, target_is_directory=True)

        utils._collapse_redundant_root(out)

        # The collapse must NOT fire: out is unchanged and still a real dir
        # holding the symlink (not replaced by a bare symlink).
        self.assertTrue(out.is_dir() and not out.is_symlink())
        self.assertTrue(link.is_symlink())
        self.assertEqual([p.name for p in out.iterdir()], ["linked"])

    def test_rollback_on_second_rename_failure(self):
        from unittest.mock import patch

        out = Path(self.test_dir) / "555555"
        inner = out / "555555"
        inner.mkdir(parents=True)
        (inner / "a.txt").write_text("hi")

        real_rename = Path.rename
        calls = {"n": 0}

        def flaky_rename(self, target):
            calls["n"] += 1
            if calls["n"] == 2:  # the inner -> output_dir rename
                raise OSError("boom")
            return real_rename(self, target)

        with patch.object(Path, "rename", flaky_rename), self.assertRaises(OSError):
            utils._collapse_redundant_root(out)

        # output_dir is restored to its original (un-collapsed) state...
        self.assertTrue((out / "555555" / "a.txt").exists())
        # ...and no stray .tmp wrapper is left behind.
        self.assertFalse((Path(self.test_dir) / "555555.tmp").exists())


class TestExtractPstCollapsesRoot(unittest.TestCase):
    """Exercises extract_pst_archive's collapse without a real readpst/PST."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_double_root_is_collapsed(self):
        from unittest.mock import patch

        archive = Path(self.test_dir) / "555555.pst"
        archive.write_bytes(b"placeholder-pst-bytes")

        def fake_run(cmd, *args, **kwargs):
            # cmd == ["readpst", "-reD", "-o", str(o_dir), str(archive)]
            o_dir = Path(cmd[cmd.index("-o") + 1])
            # Reproduce readpst -r: it creates its OWN root dir (named after the
            # PST) inside -o, holding the mail folders.
            mail = o_dir / "555555" / "Входящие"
            mail.mkdir(parents=True)
            (mail / "0001.eml").write_text("from: a@b")

            class _R:
                returncode = 0

            return _R()

        with (
            patch.object(utils.shutil, "which", return_value="/usr/bin/readpst"),
            patch.object(utils.subprocess, "run", side_effect=fake_run),
        ):
            result = utils.extract_pst_archive(archive)

        self.assertTrue(result)
        out = archive.parent / "555555"
        # Mail folder sits directly under the unique output dir...
        self.assertTrue((out / "Входящие" / "0001.eml").exists())
        # ...and the redundant nested 555555/555555 level is gone.
        self.assertFalse((out / "555555").exists())

    def test_collapse_failure_does_not_fail_extraction(self):
        from unittest.mock import patch

        archive = Path(self.test_dir) / "555555.pst"
        archive.write_bytes(b"placeholder-pst-bytes")

        def fake_run(cmd, *args, **kwargs):
            o_dir = Path(cmd[cmd.index("-o") + 1])
            mail = o_dir / "555555" / "Входящие"
            mail.mkdir(parents=True)
            (mail / "1.eml").write_text("from: a@b")

            class _R:
                returncode = 0

            return _R()

        with (
            patch.object(utils.shutil, "which", return_value="/usr/bin/readpst"),
            patch.object(utils.subprocess, "run", side_effect=fake_run),
            patch.object(utils, "_collapse_redundant_root", side_effect=OSError("boom")),
        ):
            result = utils.extract_pst_archive(archive)

        # Collapse blew up, but the extraction still reports success.
        self.assertTrue(result)

    def test_empty_extraction_returns_false_and_keeps_source(self):
        from unittest.mock import patch

        archive = Path(self.test_dir) / "555555.pst"
        archive.write_bytes(b"placeholder-pst-bytes")

        def fake_run(cmd, *args, **kwargs):
            o_dir = Path(cmd[cmd.index("-o") + 1])
            # readpst exits 0 but produces only an empty folder tree (no files).
            (o_dir / "555555" / "EmptyFolder").mkdir(parents=True)

            class _R:
                returncode = 0

            return _R()

        with (
            patch.object(utils.shutil, "which", return_value="/usr/bin/readpst"),
            patch.object(utils.subprocess, "run", side_effect=fake_run),
        ):
            result = utils.extract_pst_archive(archive)

        self.assertFalse(result)
        # The source archive is left in place for the caller to keep.
        self.assertTrue(archive.exists())

    def test_collapse_rollback_through_extract_keeps_data_and_succeeds(self):
        from unittest.mock import patch

        archive = Path(self.test_dir) / "555555.pst"
        archive.write_bytes(b"placeholder-pst-bytes")

        def fake_run(cmd, *args, **kwargs):
            o_dir = Path(cmd[cmd.index("-o") + 1])
            mail = o_dir / "555555" / "Входящие"
            mail.mkdir(parents=True)
            (mail / "1.eml").write_text("from: a@b")

            class _R:
                returncode = 0

            return _R()

        real_rename = Path.rename
        calls = {"n": 0}

        def flaky_rename(self, target):
            calls["n"] += 1
            if calls["n"] == 2:  # the inner -> output_dir rename inside the collapse
                raise OSError("boom")
            return real_rename(self, target)

        with (
            patch.object(utils.shutil, "which", return_value="/usr/bin/readpst"),
            patch.object(utils.subprocess, "run", side_effect=fake_run),
            patch.object(Path, "rename", flaky_rename),
        ):
            result = utils.extract_pst_archive(archive)

        out = archive.parent / "555555"
        # Collapse failed and rolled back, but output exists -> success is honest.
        self.assertTrue(result)
        # Data is intact in the restored (un-collapsed) layout...
        self.assertTrue((out / "555555" / "Входящие" / "1.eml").exists())
        # ...with no stray .tmp wrapper left behind.
        self.assertFalse((archive.parent / "555555.tmp").exists())

    def test_ost_routes_through_outlook_extractor(self):
        from unittest.mock import patch

        archive = Path(self.test_dir) / "mailbox.ost"
        archive.write_bytes(b"!BDN" + b"\x00" * 100)
        seen = {}

        def fake_run(cmd, *args, **kwargs):
            seen["cmd"] = cmd
            o_dir = Path(cmd[cmd.index("-o") + 1])
            mail = o_dir / "mailbox" / "Inbox"
            mail.mkdir(parents=True)
            (mail / "0001.eml").write_text("from: a@b")

            class _R:
                returncode = 0

            return _R()

        with (
            patch.object(utils.shutil, "which", return_value="/usr/bin/readpst"),
            patch.object(utils.subprocess, "run", side_effect=fake_run),
        ):
            result = utils.extract_archive(archive)

        self.assertTrue(result)
        self.assertEqual(seen["cmd"][:2], ["readpst", "-reD"])
        self.assertTrue((archive.parent / "mailbox" / "Inbox" / "0001.eml").exists())

    def test_ost_missing_readpst_logs_extract_ost_action(self):
        from unittest.mock import patch

        archive = Path(self.test_dir) / "mailbox.ost"
        archive.write_bytes(b"!BDN" + b"\x00" * 100)

        with (
            patch.object(utils.shutil, "which", return_value=None),
            self.assertLogs(level="ERROR") as captured,
        ):
            result = utils.extract_outlook_archive(archive)

        self.assertFalse(result)
        self.assertTrue(any("extract_ost" in msg for msg in captured.output))

    def test_pst_alias_still_works(self):
        from unittest.mock import patch

        archive = Path(self.test_dir) / "555555.pst"
        archive.write_bytes(b"!BDN" + b"\x00" * 100)

        def fake_run(cmd, *args, **kwargs):
            o_dir = Path(cmd[cmd.index("-o") + 1])
            mail = o_dir / "555555" / "Inbox"
            mail.mkdir(parents=True)
            (mail / "0001.eml").write_text("from: a@b")

            class _R:
                returncode = 0

            return _R()

        with (
            patch.object(utils.shutil, "which", return_value="/usr/bin/readpst"),
            patch.object(utils.subprocess, "run", side_effect=fake_run),
        ):
            result = utils.extract_pst_archive(archive)

        self.assertTrue(result)


class TestGetArchiveFilesOst(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_ost_is_discovered(self):
        ost = Path(self.test_dir) / "mailbox.ost"
        ost.write_bytes(b"!BDN")
        found = utils.get_archive_files(self.test_dir, recursive=False)
        self.assertIn(ost, found)

    def test_type_filter_ost_includes_only_ost(self):
        ost = Path(self.test_dir) / "mailbox.ost"
        ost.write_bytes(b"!BDN")
        zip_path = Path(self.test_dir) / "data.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("a.txt", "x")
        found = utils.get_archive_files(self.test_dir, recursive=False, filter_types=["ost"])
        self.assertIn(ost, found)
        self.assertNotIn(zip_path, found)


class TestExtractOutlookNonZeroExit(unittest.TestCase):
    """readpst non-zero exit: strict default vs --tolerant partial output."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _archive(self, name="mailbox.ost"):
        archive = Path(self.test_dir) / name
        archive.write_bytes(b"!BDN" + b"\x00" * 100)
        return archive

    def _fake_readpst(self, returncode, *, with_output, stderr=""):
        """Returns a subprocess.run replacement mimicking readpst's exit + output."""

        def fake_run(cmd, *args, **kwargs):
            if with_output:
                o_dir = Path(cmd[cmd.index("-o") + 1])
                mail = o_dir / "mailbox" / "Inbox"
                mail.mkdir(parents=True)
                (mail / "0001.eml").write_text("from: a@b")
            return subprocess.CompletedProcess(
                cmd, returncode, stdout="Processing Folder ...", stderr=stderr
            )

        return fake_run

    def test_strict_nonzero_exit_returns_false_and_cleans_up(self):
        from unittest.mock import patch

        archive = self._archive()
        with (
            patch.object(utils.shutil, "which", return_value="/usr/bin/readpst"),
            patch.object(
                utils.subprocess, "run", side_effect=self._fake_readpst(11, with_output=True)
            ),
        ):
            result = utils.extract_outlook_archive(archive)  # tolerant defaults False

        self.assertFalse(result)
        # The partial output directory is removed on a strict failure...
        self.assertFalse((Path(self.test_dir) / "mailbox").exists())
        # ...and the source archive is left untouched for the caller to keep.
        self.assertTrue(archive.exists())

    def test_strict_nonzero_exit_logs_readpst_diagnostics(self):
        from unittest.mock import patch

        archive = self._archive()
        with (
            patch.object(utils.shutil, "which", return_value="/usr/bin/readpst"),
            patch.object(
                utils.subprocess,
                "run",
                side_effect=self._fake_readpst(
                    11, with_output=True, stderr="libpst: pst_decode failed"
                ),
            ),
            self.assertLogs(level="ERROR") as captured,
        ):
            utils.extract_outlook_archive(archive)

        joined = "\n".join(captured.output)
        self.assertIn("libpst: pst_decode failed", joined)
        self.assertIn("11", joined)

    def test_tolerant_nonzero_exit_keeps_partial_output_and_succeeds(self):
        from unittest.mock import patch

        archive = self._archive()
        with (
            patch.object(utils.shutil, "which", return_value="/usr/bin/readpst"),
            patch.object(
                utils.subprocess, "run", side_effect=self._fake_readpst(11, with_output=True)
            ),
            self.assertLogs(level="WARNING") as captured,
        ):
            result = utils.extract_outlook_archive(archive, tolerant=True)

        self.assertTrue(result)
        # Partial output is preserved and the redundant root is still collapsed.
        out = Path(self.test_dir) / "mailbox"
        self.assertTrue((out / "Inbox" / "0001.eml").exists())
        self.assertTrue(any("partial_extraction" in m for m in captured.output))

    def test_tolerant_nonzero_exit_without_output_returns_false(self):
        from unittest.mock import patch

        archive = self._archive()
        with (
            patch.object(utils.shutil, "which", return_value="/usr/bin/readpst"),
            patch.object(
                utils.subprocess, "run", side_effect=self._fake_readpst(11, with_output=False)
            ),
        ):
            result = utils.extract_outlook_archive(archive, tolerant=True)

        self.assertFalse(result)
        self.assertTrue(archive.exists())

    def test_extract_archive_forwards_tolerant(self):
        from unittest.mock import patch

        strict = self._archive("strict.ost")
        with (
            patch.object(utils.shutil, "which", return_value="/usr/bin/readpst"),
            patch.object(
                utils.subprocess, "run", side_effect=self._fake_readpst(11, with_output=True)
            ),
        ):
            self.assertFalse(utils.extract_archive(strict))  # default strict -> False

        lenient = self._archive("lenient.ost")
        with (
            patch.object(utils.shutil, "which", return_value="/usr/bin/readpst"),
            patch.object(
                utils.subprocess, "run", side_effect=self._fake_readpst(11, with_output=True)
            ),
        ):
            self.assertTrue(utils.extract_archive(lenient, tolerant=True))  # forwarded -> True


if __name__ == "__main__":
    unittest.main()
