import errno
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from empty.main import (
    find_empty_directories,
    is_directory_empty,
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

        self.assertTrue(is_directory_empty(empty_dir))

    def test_non_empty_directory_with_file(self):
        """Test that a directory with files is not empty."""
        non_empty = self.test_path / "non_empty"
        non_empty.mkdir()
        (non_empty / "file.txt").touch()

        self.assertFalse(is_directory_empty(non_empty))

    def test_non_empty_directory_with_subdir(self):
        """Test that a directory with subdirectories is not empty."""
        non_empty = self.test_path / "non_empty"
        non_empty.mkdir()
        (non_empty / "subdir").mkdir()

        self.assertFalse(is_directory_empty(non_empty))

    def test_directory_with_hidden_files(self):
        """Test that a directory holding only a hidden file is not empty."""
        dir_with_hidden = self.test_path / "hidden"
        dir_with_hidden.mkdir()
        (dir_with_hidden / ".hidden").touch()

        self.assertFalse(is_directory_empty(dir_with_hidden))


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

    def test_dir_holding_only_a_hidden_file_is_not_empty(self):
        """A directory whose only entry is hidden still holds data."""
        only_hidden = self.test_path / "only_hidden"
        only_hidden.mkdir()
        (only_hidden / ".DS_Store").touch()

        empty_dirs = find_empty_directories(self.test_dir, recursive=True, include_hidden=False)

        self.assertNotIn("only_hidden", {d.name for d in empty_dirs})

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

    def test_unrelated_oserror_is_reported(self):
        """An OSError that merely mentions 'not empty' is still a real error."""
        target = self.test_path / "target"
        target.mkdir()

        with mock.patch.object(Path, "rmdir", side_effect=OSError(errno.EIO, "buffer not empty")):
            with self.assertLogs(level="ERROR"):
                removed, skipped = remove_empty_directories([target])

        self.assertEqual((removed, skipped), (0, 1))

    def test_remove_nonexistent_fails_gracefully(self):
        """Test that removing nonexistent directory fails gracefully."""
        nonexistent = self.test_path / "nonexistent"

        removed, skipped = remove_empty_directories([nonexistent])

        self.assertEqual(removed, 0)
        self.assertEqual(skipped, 1)


class TestEmptySkipsTrash(unittest.TestCase):
    """Tests that the empty finder never reports anything under .pystou-trash."""

    def setUp(self):
        """Set up a temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_empty_ignores_trash(self):
        """An empty dir inside .pystou-trash must not be reported, even bottom-up."""
        # Genuinely empty directory inside the trash - WOULD be reported if not excluded
        (self.test_path / ".pystou-trash" / "r" / "0").mkdir(parents=True)
        # Normal sibling that SHOULD be found
        (self.test_path / "really_empty").mkdir()

        found = [str(p) for p in find_empty_directories(self.test_dir, True, True)]

        self.assertTrue(any("really_empty" in p for p in found))
        self.assertFalse(any(".pystou-trash" in p for p in found))

    def test_empty_ignores_trash_non_recursive(self):
        """The non-recursive scandir branch must also skip .pystou-trash."""
        (self.test_path / ".pystou-trash").mkdir()
        (self.test_path / "really_empty").mkdir()

        found = [str(p) for p in find_empty_directories(self.test_dir, False, True)]

        self.assertTrue(any("really_empty" in p for p in found))
        self.assertFalse(any(".pystou-trash" in p for p in found))


if __name__ == "__main__":
    unittest.main()
