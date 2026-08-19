import shutil
import tempfile
import unittest
from pathlib import Path

from common import trash
from common.fs_walker import collect_directories
from common.indexer import initialize_database
from extract.main import delete_archive_file, update_index_after_extraction


class TestExtractQuarantine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_delete_archive_quarantines_by_default(self):
        arc = Path(self.test_dir) / "a.zip"
        arc.write_text("PK")
        conn = initialize_database(self.test_dir)
        delete_archive_file(arc, conn, dry_run=False, op_root=self.test_dir, hard_delete=False)
        conn.close()
        self.assertFalse(arc.exists())
        self.assertEqual(len(trash.list_runs(self.test_dir)), 1)

    def test_delete_archive_hard_delete(self):
        arc = Path(self.test_dir) / "a.zip"
        arc.write_text("PK")
        conn = initialize_database(self.test_dir)
        delete_archive_file(arc, conn, dry_run=False, op_root=self.test_dir, hard_delete=True)
        conn.close()
        self.assertFalse(arc.exists())
        self.assertEqual(trash.list_runs(self.test_dir), [])


class TestUpdateIndexAfterExtraction(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.root = Path(self.test_dir)
        self.conn = initialize_database(self.test_dir)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _indexed_dirs(self) -> set:
        return {Path(row[0]) for row in self.conn.execute("SELECT path FROM directories")}

    def test_existing_index_is_not_wiped(self):
        (self.root / "a").mkdir()
        (self.root / "b").mkdir()
        collect_directories(self.conn, self.test_dir, recursive=True)
        before = self._indexed_dirs()
        self.assertEqual(before, {self.root / "a", self.root / "b"})

        update_index_after_extraction(self.conn, self.root / "a")

        self.assertEqual(self._indexed_dirs(), before)

    def test_new_entries_are_indexed(self):
        collect_directories(self.conn, self.test_dir, recursive=True)
        (self.root / "out").mkdir()
        (self.root / "new.txt").write_text("hi")

        update_index_after_extraction(self.conn, self.root)

        self.assertIn(self.root / "out", self._indexed_dirs())
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM files WHERE directory_path = ?", (str(self.root),))
        self.assertIn("new.txt", {row[0] for row in cursor})


if __name__ == "__main__":
    unittest.main()
