import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from common import trash
from common.fs_walker import collect_directories
from common.indexer import close_database, initialize_database
from common.utils import group_directories
from dedup_folders.main import (
    delete_duplicates,
    identify_base_and_duplicates,
    merge_contents,
)


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
    def test_delete_duplicates_removes_dups(self, mock_print):
        # Exercise the still-present delete_duplicates core logic.
        groups = group_directories(self.conn)
        for _group_key, dir_paths in groups.items():
            _base, dups = identify_base_and_duplicates(dir_paths)
            delete_duplicates(
                dups, dry_run=False, conn=self.conn, op_root=self.test_dir, hard_delete=True
            )
        self.assertFalse((Path(self.test_dir) / "folder (1)").exists())
        self.assertFalse((Path(self.test_dir) / "folder (2)").exists())
        self.assertTrue((Path(self.test_dir) / "folder").exists())

    @patch("builtins.print")
    def test_merge_contents_merges_dups(self, mock_print):
        # Exercise the still-present merge_contents core logic.
        groups = group_directories(self.conn)
        for _group_key, dir_paths in groups.items():
            base, dups = identify_base_and_duplicates(dir_paths)
            merge_contents(
                base, dups, dry_run=False, conn=self.conn, op_root=self.test_dir, hard_delete=True
            )
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


class TestDedupQuarantine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_delete_duplicates_quarantines(self):
        dup = Path(self.test_dir) / "dup (1)"
        dup.mkdir()
        (dup / "f.txt").write_text("x")
        conn = initialize_database(self.test_dir)
        delete_duplicates([dup], dry_run=False, conn=conn, op_root=self.test_dir, hard_delete=False)
        conn.close()
        self.assertFalse(dup.exists())
        self.assertEqual(len(trash.list_runs(self.test_dir)), 1)

    def test_delete_duplicates_hard_delete(self):
        dup = Path(self.test_dir) / "dup (1)"
        dup.mkdir()
        conn = initialize_database(self.test_dir)
        delete_duplicates([dup], dry_run=False, conn=conn, op_root=self.test_dir, hard_delete=True)
        conn.close()
        self.assertFalse(dup.exists())
        self.assertEqual(trash.list_runs(self.test_dir), [])

    def test_merge_contents_quarantines_merged_dup(self):
        base = Path(self.test_dir) / "base"
        base.mkdir()
        (base / "keep.txt").write_text("base")
        dup = Path(self.test_dir) / "base (1)"
        dup.mkdir()
        (dup / "only_in_dup.txt").write_text("dup")  # no conflict -> moves cleanly
        conn = initialize_database(self.test_dir)
        merge_contents(
            base, [dup], dry_run=False, conn=conn, op_root=self.test_dir, hard_delete=False
        )
        conn.close()
        self.assertTrue((base / "only_in_dup.txt").is_file())  # merged into base
        self.assertFalse(dup.exists())  # dup dir removed
        self.assertEqual(len(trash.list_runs(self.test_dir)), 1)  # quarantined, not deleted


if __name__ == "__main__":
    unittest.main()
