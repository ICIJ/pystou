import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

from cleanup.main import (
    find_junk,
    is_junk_file,
    remove_junk,
    JUNK_FILES,
    JUNK_DIRS,
    main,
)


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
        junk = find_junk(
            self.test_dir, recursive=False, junk_files=JUNK_FILES, junk_dirs=JUNK_DIRS
        )
        junk_names = {j.name for j in junk}

        self.assertIn(".DS_Store", junk_names)
        self.assertIn("Thumbs.db", junk_names)
        self.assertIn("._resource", junk_names)
        self.assertIn("__MACOSX", junk_names)
        self.assertNotIn("document.txt", junk_names)

    def test_find_junk_recursive(self):
        """Test finding junk files with recursion."""
        junk = find_junk(
            self.test_dir, recursive=True, junk_files=JUNK_FILES, junk_dirs=JUNK_DIRS
        )

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

        removed, skipped = remove_junk([junk_file])

        self.assertEqual(removed, 1)
        self.assertEqual(skipped, 0)
        self.assertFalse(junk_file.exists())

    def test_remove_junk_directory(self):
        """Test removing junk directories."""
        junk_dir = self.test_path / "__MACOSX"
        junk_dir.mkdir()
        (junk_dir / "file.txt").touch()

        removed, skipped = remove_junk([junk_dir])

        self.assertEqual(removed, 1)
        self.assertEqual(skipped, 0)
        self.assertFalse(junk_dir.exists())

    def test_remove_junk_mixed(self):
        """Test removing mixed junk files and directories."""
        junk_file = self.test_path / ".DS_Store"
        junk_file.touch()
        junk_dir = self.test_path / "__MACOSX"
        junk_dir.mkdir()

        removed, skipped = remove_junk([junk_file, junk_dir])

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


class TestCleanupMain(unittest.TestCase):
    """Tests for the main cleanup function."""

    def setUp(self):
        """Set up a temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    @patch("builtins.print")
    def test_main_no_junk(self, mock_print):
        """Test main when no junk files are found."""
        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "include": None,
                "list_only": False,
            },
        )
        main(args)

        # Should print "No junk files found."
        mock_print.assert_called_with("No junk files found.")

    @patch("builtins.print")
    def test_main_list_only(self, mock_print):
        """Test main with --list-only flag."""
        (self.test_path / ".DS_Store").touch()

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "include": None,
                "list_only": True,
            },
        )
        main(args)

        # File should still exist
        self.assertTrue((self.test_path / ".DS_Store").exists())

    @patch("builtins.print")
    def test_main_dry_run(self, mock_print):
        """Test main with --dry-run flag."""
        (self.test_path / ".DS_Store").touch()

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": True,
                "log_dir": self.test_dir,
                "include": None,
                "list_only": False,
            },
        )
        main(args)

        # File should still exist
        self.assertTrue((self.test_path / ".DS_Store").exists())

    @patch("builtins.print")
    def test_main_remove_junk(self, mock_print):
        """Test main actually removes junk files."""
        (self.test_path / ".DS_Store").touch()
        (self.test_path / "Thumbs.db").touch()

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "include": None,
                "list_only": False,
            },
        )
        main(args)

        # Files should be removed
        self.assertFalse((self.test_path / ".DS_Store").exists())
        self.assertFalse((self.test_path / "Thumbs.db").exists())

    @patch("builtins.print")
    def test_main_with_include(self, mock_print):
        """Test main with --include flag."""
        (self.test_path / "custom.tmp").touch()

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "include": ["custom.tmp"],
                "list_only": False,
            },
        )
        main(args)

        # Custom file should be removed
        self.assertFalse((self.test_path / "custom.tmp").exists())


if __name__ == "__main__":
    unittest.main()
