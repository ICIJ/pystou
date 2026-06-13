import shutil
import tempfile
import unittest
from pathlib import Path

from common import trash
from common.indexer import initialize_database
from extract.main import delete_archive_file


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


if __name__ == "__main__":
    unittest.main()
