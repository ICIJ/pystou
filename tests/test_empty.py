import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from empty.main import (
    find_empty_directories,
    is_directory_empty,
    main,
    remove_empty_directories,
)


class TestEmptyIsDirectoryEmpty(unittest.TestCase):
    """Tests for checking if a directory is empty."""

    def setUp(self):
        """Set up a temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_empty_directory(self):
        """Test that an empty directory is detected."""
        empty_dir = self.test_path / "empty"
        empty_dir.mkdir()

        self.assertTrue(is_directory_empty(empty_dir, include_hidden=True))

    def test_non_empty_directory_with_file(self):
        """Test that a directory with files is not empty."""
        non_empty = self.test_path / "non_empty"
        non_empty.mkdir()
        (non_empty / "file.txt").touch()

        self.assertFalse(is_directory_empty(non_empty, include_hidden=True))

    def test_non_empty_directory_with_subdir(self):
        """Test that a directory with subdirectories is not empty."""
        non_empty = self.test_path / "non_empty"
        non_empty.mkdir()
        (non_empty / "subdir").mkdir()

        self.assertFalse(is_directory_empty(non_empty, include_hidden=True))

    def test_directory_with_hidden_files_include(self):
        """Test directory with hidden files when including hidden."""
        dir_with_hidden = self.test_path / "hidden"
        dir_with_hidden.mkdir()
        (dir_with_hidden / ".hidden").touch()

        self.assertFalse(is_directory_empty(dir_with_hidden, include_hidden=True))

    def test_directory_with_hidden_files_exclude(self):
        """Test directory with hidden files when excluding hidden."""
        dir_with_hidden = self.test_path / "hidden"
        dir_with_hidden.mkdir()
        (dir_with_hidden / ".hidden").touch()

        # Should be considered empty when excluding hidden files
        self.assertTrue(is_directory_empty(dir_with_hidden, include_hidden=False))


class TestEmptyFindEmptyDirectories(unittest.TestCase):
    """Tests for finding empty directories."""

    def setUp(self):
        """Set up a temporary directory structure."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        # Create empty directories
        (self.test_path / "empty1").mkdir()
        (self.test_path / "empty2").mkdir()

        # Create non-empty directory
        non_empty = self.test_path / "non_empty"
        non_empty.mkdir()
        (non_empty / "file.txt").touch()

        # Create nested structure with empty leaf
        nested = self.test_path / "nested"
        nested.mkdir()
        (nested / "file.txt").touch()
        (nested / "empty_child").mkdir()

        # Create hidden empty directory
        (self.test_path / ".hidden_empty").mkdir()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_find_empty_non_recursive(self):
        """Test finding empty directories without recursion."""
        empty_dirs = find_empty_directories(self.test_dir, recursive=False, include_hidden=False)

        dir_names = {d.name for d in empty_dirs}
        self.assertIn("empty1", dir_names)
        self.assertIn("empty2", dir_names)
        self.assertNotIn("non_empty", dir_names)
        self.assertNotIn(".hidden_empty", dir_names)

    def test_find_empty_recursive(self):
        """Test finding empty directories with recursion."""
        empty_dirs = find_empty_directories(self.test_dir, recursive=True, include_hidden=False)

        dir_names = {d.name for d in empty_dirs}
        self.assertIn("empty1", dir_names)
        self.assertIn("empty2", dir_names)
        self.assertIn("empty_child", dir_names)

    def test_find_empty_include_hidden(self):
        """Test finding empty directories including hidden."""
        empty_dirs = find_empty_directories(self.test_dir, recursive=False, include_hidden=True)

        dir_names = {d.name for d in empty_dirs}
        self.assertIn(".hidden_empty", dir_names)

    def test_find_empty_sorted_deepest_first(self):
        """Test that empty directories are sorted deepest first."""
        # Create deeper nested structure
        deep = self.test_path / "a" / "b" / "c"
        deep.mkdir(parents=True)

        empty_dirs = find_empty_directories(self.test_dir, recursive=True, include_hidden=False)

        # First directories should be the deepest
        if len(empty_dirs) > 1:
            depths = [len(d.parts) for d in empty_dirs]
            self.assertEqual(depths, sorted(depths, reverse=True))


class TestEmptyRemoveEmptyDirectories(unittest.TestCase):
    """Tests for removing empty directories."""

    def setUp(self):
        """Set up a temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_remove_single_empty(self):
        """Test removing a single empty directory."""
        empty_dir = self.test_path / "empty"
        empty_dir.mkdir()

        removed, skipped = remove_empty_directories([empty_dir])

        self.assertEqual(removed, 1)
        self.assertEqual(skipped, 0)
        self.assertFalse(empty_dir.exists())

    def test_remove_multiple_empty(self):
        """Test removing multiple empty directories."""
        empty1 = self.test_path / "empty1"
        empty2 = self.test_path / "empty2"
        empty1.mkdir()
        empty2.mkdir()

        removed, skipped = remove_empty_directories([empty1, empty2])

        self.assertEqual(removed, 2)
        self.assertEqual(skipped, 0)
        self.assertFalse(empty1.exists())
        self.assertFalse(empty2.exists())

    def test_remove_nested_deepest_first(self):
        """Test removing nested empty directories deepest first."""
        # Create a->b->c structure (all empty)
        a = self.test_path / "a"
        b = a / "b"
        c = b / "c"
        c.mkdir(parents=True)

        # Must be sorted deepest first for correct removal
        empty_dirs = [c, b, a]
        removed, skipped = remove_empty_directories(empty_dirs)

        self.assertEqual(removed, 3)
        self.assertEqual(skipped, 0)
        self.assertFalse(a.exists())

    def test_remove_non_empty_fails_gracefully(self):
        """Test that removing non-empty directory fails gracefully."""
        non_empty = self.test_path / "non_empty"
        non_empty.mkdir()
        (non_empty / "file.txt").touch()

        removed, skipped = remove_empty_directories([non_empty])

        self.assertEqual(removed, 0)
        self.assertEqual(skipped, 1)
        self.assertTrue(non_empty.exists())

    def test_remove_nonexistent_fails_gracefully(self):
        """Test that removing nonexistent directory fails gracefully."""
        nonexistent = self.test_path / "nonexistent"

        removed, skipped = remove_empty_directories([nonexistent])

        self.assertEqual(removed, 0)
        self.assertEqual(skipped, 1)


class TestEmptyMain(unittest.TestCase):
    """Tests for the main empty function."""

    def setUp(self):
        """Set up a temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    @patch("builtins.print")
    def test_main_no_empty(self, mock_print):
        """Test main when no empty directories are found."""
        # Create a non-empty directory
        non_empty = self.test_path / "non_empty"
        non_empty.mkdir()
        (non_empty / "file.txt").touch()

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "list_only": False,
                "include_hidden": False,
            },
        )
        main(args)

        mock_print.assert_called_with("No empty directories found.")

    @patch("builtins.print")
    def test_main_list_only(self, mock_print):
        """Test main with --list-only flag."""
        empty_dir = self.test_path / "empty"
        empty_dir.mkdir()

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "list_only": True,
                "include_hidden": False,
            },
        )
        main(args)

        # Directory should still exist
        self.assertTrue(empty_dir.exists())

    @patch("builtins.print")
    def test_main_dry_run(self, mock_print):
        """Test main with --dry-run flag."""
        empty_dir = self.test_path / "empty"
        empty_dir.mkdir()

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": True,
                "log_dir": self.test_dir,
                "list_only": False,
                "include_hidden": False,
            },
        )
        main(args)

        # Directory should still exist
        self.assertTrue(empty_dir.exists())

    @patch("builtins.print")
    def test_main_remove_empty(self, mock_print):
        """Test main actually removes empty directories."""
        empty1 = self.test_path / "empty1"
        empty2 = self.test_path / "empty2"
        empty1.mkdir()
        empty2.mkdir()

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "list_only": False,
                "include_hidden": False,
            },
        )
        main(args)

        # Directories should be removed
        self.assertFalse(empty1.exists())
        self.assertFalse(empty2.exists())

    @patch("builtins.print")
    def test_main_recursive(self, mock_print):
        """Test main with recursive flag."""
        # Create nested empty
        nested = self.test_path / "parent"
        nested.mkdir()
        (nested / "file.txt").touch()
        child_empty = nested / "child_empty"
        child_empty.mkdir()

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": True,
                "dry_run": False,
                "log_dir": self.test_dir,
                "list_only": False,
                "include_hidden": False,
            },
        )
        main(args)

        # Child empty should be removed
        self.assertFalse(child_empty.exists())
        # Parent should still exist (has file)
        self.assertTrue(nested.exists())

    @patch("builtins.print")
    def test_main_include_hidden(self, mock_print):
        """Test main with --include-hidden flag."""
        hidden_empty = self.test_path / ".hidden_empty"
        hidden_empty.mkdir()

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "list_only": False,
                "include_hidden": True,
            },
        )
        main(args)

        # Hidden directory should be removed
        self.assertFalse(hidden_empty.exists())


if __name__ == "__main__":
    unittest.main()
