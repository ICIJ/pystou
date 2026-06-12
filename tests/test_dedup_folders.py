import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

from common.fs_walker import collect_directories
from common.indexer import close_database, initialize_database
from common.utils import group_directories
from dedup_folders.main import identify_base_and_duplicates, manage_index, process_group


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


import shutil as _shutil
import tempfile as _tempfile
from pathlib import Path as _Path
from unittest.mock import patch as _patch

from common.indexer import close_database as _close_db
from common.indexer import initialize_database as _init_db
from dedup_folders.main import merge_contents


class TestMergeConflictPreservesData(unittest.TestCase):
    def setUp(self):
        self.test_dir = _tempfile.mkdtemp()
        self.conn = _init_db(self.test_dir)
        self.base = _Path(self.test_dir) / "base"
        self.dup = _Path(self.test_dir) / "base (1)"
        self.base.mkdir()
        self.dup.mkdir()
        # Conflicting filename present in both, with different content.
        (self.base / "shared.txt").write_text("base-version")
        (self.dup / "shared.txt").write_text("dup-version")

    def tearDown(self):
        _close_db(self.conn)
        _shutil.rmtree(self.test_dir, ignore_errors=True)

    @_patch("builtins.print")
    def test_conflicting_file_is_not_destroyed(self, mock_print):
        merge_contents(self.base, [self.dup], dry_run=False, conn=self.conn)
        # Because of the conflict, the duplicate dir must be preserved...
        self.assertTrue(self.dup.exists())
        # ...and the conflicting file inside it must still exist.
        self.assertTrue((self.dup / "shared.txt").exists())
        self.assertEqual((self.dup / "shared.txt").read_text(), "dup-version")
        # Base copy is untouched.
        self.assertEqual((self.base / "shared.txt").read_text(), "base-version")


class TestDedupManageIndex(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.conn = initialize_database(self.test_dir)
        self.args = SimpleNamespace(directory=self.test_dir, recursive=True, level=None)

    def tearDown(self):
        close_database(self.conn)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _populate(self):
        self.conn.execute(
            "INSERT INTO directories (path, parent_path, mtime) VALUES ('/a', '/', 0)"
        )
        self.conn.commit()

    @mock.patch("dedup_folders.main.collect_directories")
    @mock.patch("dedup_folders.main.prompt_use_existing_index")
    def test_no_file_scans_without_prompt(self, prompt, collect):
        manage_index(self.conn, self.args, index_existed=False)
        prompt.assert_not_called()
        collect.assert_called_once()

    @mock.patch("dedup_folders.main.collect_directories")
    @mock.patch("dedup_folders.main.prompt_use_existing_index")
    def test_empty_file_scans_without_prompt(self, prompt, collect):
        manage_index(self.conn, self.args, index_existed=True)
        prompt.assert_not_called()
        collect.assert_called_once()

    @mock.patch("dedup_folders.main.collect_directories")
    @mock.patch("dedup_folders.main.prompt_use_existing_index", return_value=True)
    def test_populated_file_reused_skips_scan(self, prompt, collect):
        self._populate()
        manage_index(self.conn, self.args, index_existed=True)
        prompt.assert_called_once()
        collect.assert_not_called()

    @mock.patch("dedup_folders.main.collect_directories")
    @mock.patch("dedup_folders.main.prompt_use_existing_index", return_value=False)
    def test_populated_file_rescan_calls_collect(self, prompt, collect):
        self._populate()
        manage_index(self.conn, self.args, index_existed=True)
        prompt.assert_called_once()
        collect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
