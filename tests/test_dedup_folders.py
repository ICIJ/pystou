import unittest
import tempfile
import shutil
import os
from pathlib import Path
from unittest.mock import patch
from dedup_folders.main import identify_base_and_duplicates, process_group
from common.indexer import initialize_database, close_database
from common.fs_walker import collect_directories
from common.utils import group_directories


class TestDedupFolders(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        # Set up test directories
        self.setup_test_directories()
        # Initialize database
        self.db_path = os.path.join(self.test_dir, "filesystem_index.db")
        self.conn = initialize_database(self.test_dir)
        # Collect directories
        collect_directories(self.conn, self.test_dir, recursive=True)

    def tearDown(self):
        # Close database connection
        close_database(self.conn)
        # Remove temporary directory
        shutil.rmtree(self.test_dir)

    def setup_test_directories(self):
        # Create duplicate directories
        base_dir = Path(self.test_dir) / "folder"
        dup_dir_1 = Path(self.test_dir) / "folder (1)"
        dup_dir_2 = Path(self.test_dir) / "folder (2)"
        base_dir.mkdir()
        dup_dir_1.mkdir()
        dup_dir_2.mkdir()
        # Create files in base directory
        (base_dir / "file1.txt").touch()
        (base_dir / "file2.txt").touch()
        # Create files in duplicate directories
        (dup_dir_1 / "file3.txt").touch()
        (dup_dir_2 / "file4.txt").touch()

    @patch("builtins.print")
    def test_identify_base_and_duplicates(self, mock_print):
        dir_paths = [
            Path(self.test_dir) / "folder",
            Path(self.test_dir) / "folder (1)",
            Path(self.test_dir) / "folder (2)",
        ]
        base_dir, duplicate_dirs = identify_base_and_duplicates(dir_paths)
        self.assertEqual(base_dir.name, "folder")
        self.assertEqual(len(duplicate_dirs), 2)

    @patch("builtins.print")
    def test_process_group_delete(self, mock_print):
        # Simulate user choice to delete duplicates
        args = type("Args", (), {"dry_run": False, "default_choice": 1})
        groups = group_directories(self.conn)
        for group_key, dir_paths in groups.items():
            process_group(group_key, dir_paths, args, self.conn)
        # Check that duplicate directories are deleted
        self.assertFalse((Path(self.test_dir) / "folder (1)").exists())
        self.assertFalse((Path(self.test_dir) / "folder (2)").exists())
        self.assertTrue((Path(self.test_dir) / "folder").exists())

    @patch("builtins.print")
    def test_process_group_merge(self, mock_print):
        # Reset test directories
        self.tearDown()
        self.setUp()
        # Simulate user choice to merge duplicates
        args = type("Args", (), {"dry_run": False, "default_choice": 2})
        groups = group_directories(self.conn)
        for group_key, dir_paths in groups.items():
            process_group(group_key, dir_paths, args, self.conn)
        # Check that duplicate directories are deleted
        self.assertFalse((Path(self.test_dir) / "folder (1)").exists())
        self.assertFalse((Path(self.test_dir) / "folder (2)").exists())
        self.assertTrue((Path(self.test_dir) / "folder").exists())
        # Check that files from duplicates are moved to base directory
        self.assertTrue((Path(self.test_dir) / "folder" / "file3.txt").exists())
        self.assertTrue((Path(self.test_dir) / "folder" / "file4.txt").exists())


if __name__ == "__main__":
    unittest.main()
