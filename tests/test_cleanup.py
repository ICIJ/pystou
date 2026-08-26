import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cleanup.main import (
    JUNK_DIRS,
    JUNK_FILES,
    find_junk,
    is_junk_file,
    remove_junk,
)
from common import trash


class TestCleanupJunkDetection(unittest.TestCase):
    """Tests for junk file detection functions."""

    def test_is_junk_file_ds_store(self):
        """Test that .DS_Store is detected as junk."""
        self.assertTrue(is_junk_file(".DS_Store", JUNK_FILES))

    def test_is_junk_file_thumbs_db(self):
        """Test that Thumbs.db is detected as junk."""
        self.assertTrue(is_junk_file("Thumbs.db", JUNK_FILES))

    def test_is_junk_file_desktop_ini(self):
        """Test that desktop.ini is detected as junk."""
        self.assertTrue(is_junk_file("desktop.ini", JUNK_FILES))

    def test_is_junk_file_prefix(self):
        """Test that files with ._ prefix are detected as junk."""
        self.assertTrue(is_junk_file("._somefile.txt", JUNK_FILES))

    def test_is_not_junk_file(self):
        """Test that regular files are not detected as junk."""
        self.assertFalse(is_junk_file("document.txt", JUNK_FILES))
        self.assertFalse(is_junk_file("image.png", JUNK_FILES))

    def test_is_junk_file_custom_pattern(self):
        """Test that custom patterns are detected as junk."""
        custom_junk = JUNK_FILES.copy()
        custom_junk.add("custom.junk")
        self.assertTrue(is_junk_file("custom.junk", custom_junk))


class TestCleanupFindJunk(unittest.TestCase):
    """Tests for finding junk files in directories."""

    def setUp(self):
        """Set up a temporary directory with junk files."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        # Create junk files
        (self.test_path / ".DS_Store").touch()
        (self.test_path / "Thumbs.db").touch()
        (self.test_path / "._resource").touch()

        # Create regular files
        (self.test_path / "document.txt").touch()
        (self.test_path / "image.png").touch()

        # Create junk directory
        (self.test_path / "__MACOSX").mkdir()
        (self.test_path / "__MACOSX" / "file.txt").touch()

        # Create subdirectory with junk
        subdir = self.test_path / "subdir"
        subdir.mkdir()
        (subdir / ".DS_Store").touch()
        (subdir / "normal.txt").touch()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_find_junk_non_recursive(self):
        """Test finding junk files without recursion."""
        junk = find_junk(self.test_dir, recursive=False, junk_files=JUNK_FILES, junk_dirs=JUNK_DIRS)
        junk_names = {j.name for j in junk}

        self.assertIn(".DS_Store", junk_names)
        self.assertIn("Thumbs.db", junk_names)
        self.assertIn("._resource", junk_names)
        self.assertIn("__MACOSX", junk_names)
        self.assertNotIn("document.txt", junk_names)

    def test_find_junk_recursive(self):
        """Test finding junk files with recursion."""
        junk = find_junk(self.test_dir, recursive=True, junk_files=JUNK_FILES, junk_dirs=JUNK_DIRS)

        # Should find junk in root and subdirectory
        self.assertGreaterEqual(len(junk), 4)

        # Check that subdirectory junk is found
        subdir_junk = [j for j in junk if "subdir" in str(j)]
        self.assertGreater(len(subdir_junk), 0)

    def test_find_junk_custom_pattern(self):
        """Test finding junk with custom patterns."""
        # Create a file matching custom pattern
        (self.test_path / "custom.bak").touch()

        custom_junk = JUNK_FILES.copy()
        custom_junk.add("custom.bak")

        junk = find_junk(
            self.test_dir, recursive=False, junk_files=custom_junk, junk_dirs=JUNK_DIRS
        )
        junk_names = {j.name for j in junk}

        self.assertIn("custom.bak", junk_names)


class TestCleanupRemoveJunk(unittest.TestCase):
    """Tests for removing junk files."""

    def setUp(self):
        """Set up a temporary directory with junk files."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_remove_junk_files(self):
        """Test removing junk files."""
        junk_file = self.test_path / ".DS_Store"
        junk_file.touch()

        removed, skipped = remove_junk([junk_file], op_root=self.test_dir, hard_delete=True)

        self.assertEqual(removed, 1)
        self.assertEqual(skipped, 0)
        self.assertFalse(junk_file.exists())

    def test_remove_junk_directory(self):
        """Test removing junk directories."""
        junk_dir = self.test_path / "__MACOSX"
        junk_dir.mkdir()
        (junk_dir / "file.txt").touch()

        removed, skipped = remove_junk([junk_dir], op_root=self.test_dir, hard_delete=True)

        self.assertEqual(removed, 1)
        self.assertEqual(skipped, 0)
        self.assertFalse(junk_dir.exists())

    def test_remove_junk_mixed(self):
        """Test removing mixed junk files and directories."""
        junk_file = self.test_path / ".DS_Store"
        junk_file.touch()
        junk_dir = self.test_path / "__MACOSX"
        junk_dir.mkdir()

        removed, skipped = remove_junk(
            [junk_file, junk_dir], op_root=self.test_dir, hard_delete=True
        )

        self.assertEqual(removed, 2)
        self.assertEqual(skipped, 0)
        self.assertFalse(junk_file.exists())
        self.assertFalse(junk_dir.exists())

    def test_remove_junk_nonexistent(self):
        """Test handling of nonexistent files."""
        nonexistent = self.test_path / "nonexistent"

        removed, skipped = remove_junk([nonexistent])

        self.assertEqual(removed, 0)
        self.assertEqual(skipped, 1)


class TestCleanupQuarantine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_remove_junk_quarantines_by_default(self):
        junk = Path(self.test_dir) / ".DS_Store"
        junk.write_text("junk")
        removed, _skipped = remove_junk([junk], op_root=self.test_dir, hard_delete=False)
        self.assertEqual(removed, 1)
        self.assertFalse(junk.exists())
        self.assertEqual(len(trash.list_runs(self.test_dir)), 1)

    def test_hard_delete_really_deletes(self):
        junk = Path(self.test_dir) / ".DS_Store"
        junk.write_text("junk")
        removed, _skipped = remove_junk([junk], op_root=self.test_dir, hard_delete=True)
        self.assertEqual(removed, 1)
        self.assertFalse(junk.exists())
        self.assertEqual(trash.list_runs(self.test_dir), [])  # no run created

    def test_find_junk_skips_trash_recursive(self):
        (Path(self.test_dir) / ".pystou-trash" / "r" / "0").mkdir(parents=True)
        (Path(self.test_dir) / ".pystou-trash" / "r" / "0" / ".DS_Store").write_text("x")
        (Path(self.test_dir) / "real").mkdir()
        (Path(self.test_dir) / "real" / ".DS_Store").write_text("x")
        items = find_junk(self.test_dir, True, {".DS_Store"}, set())
        self.assertTrue(any("real" in str(p) for p in items))
        self.assertFalse(any(".pystou-trash" in str(p) for p in items))

    def test_find_junk_skips_trash_non_recursive(self):
        (Path(self.test_dir) / ".pystou-trash" / "r" / "0").mkdir(parents=True)
        (Path(self.test_dir) / ".pystou-trash" / "r" / "0" / ".DS_Store").write_text("x")
        (Path(self.test_dir) / ".DS_Store").write_text("x")
        items = find_junk(self.test_dir, False, {".DS_Store"}, set())
        self.assertTrue(any(p.name == ".DS_Store" for p in items))
        self.assertFalse(any(".pystou-trash" in str(p) for p in items))

    def test_remove_junk_trash_error_skips_all(self):
        junk = Path(self.test_dir) / ".DS_Store"
        junk.write_text("x")
        with mock.patch(
            "cleanup.main.trash.quarantine",
            side_effect=trash.TrashUnavailableError("boom"),
        ):
            removed, skipped = remove_junk([junk], op_root=self.test_dir, hard_delete=False)
        self.assertEqual(removed, 0)
        self.assertEqual(skipped, 1)
        self.assertTrue(junk.exists())  # not removed when quarantine fails

    def test_remove_junk_os_error_reports_partial_run(self):
        if os.geteuid() == 0:
            self.skipTest("requires non-root user")
        root = Path(self.test_dir)
        (root / ".DS_Store").write_text("x")
        locked = root / "locked"
        locked.mkdir()
        (locked / ".DS_Store").write_text("x")
        items = find_junk(self.test_dir, True, {".DS_Store"}, set())
        os.chmod(locked, 0o500)
        try:
            removed, skipped = remove_junk(items, op_root=self.test_dir, hard_delete=False)
        finally:
            os.chmod(locked, 0o700)
        self.assertEqual((removed, skipped), (1, 1))


if __name__ == "__main__":
    unittest.main()


class TestCleanupThreadCount(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        for i in range(5):
            sub = self.root / f"sub{i}"
            sub.mkdir()
            (sub / ".DS_Store").write_text("x")
            (sub / "keep.txt").write_text("y")
        junk_dir = self.root / "__MACOSX"
        junk_dir.mkdir()
        (junk_dir / "inside.txt").write_text("z")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_result_is_sorted_and_independent_of_worker_count(self):
        one = find_junk(str(self.root), True, JUNK_FILES, JUNK_DIRS, threads=1)
        eight = find_junk(str(self.root), True, JUNK_FILES, JUNK_DIRS, threads=8)
        self.assertEqual(one, eight)
        self.assertEqual(one, sorted(one))

    def test_junk_directory_is_reported_but_never_descended(self):
        found = find_junk(str(self.root), True, JUNK_FILES, JUNK_DIRS, threads=4)
        self.assertIn(self.root / "__MACOSX", found)
        self.assertNotIn(self.root / "__MACOSX" / "inside.txt", found)
