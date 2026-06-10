# tests/test_indexer.py
import os
import tempfile
import shutil
import unittest
from pathlib import Path

from common.indexer import (
    initialize_database,
    update_index_after_change,
    close_database,
)
from common.errors import PystouError


class TestIndexerDeleteDirectory(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.conn = initialize_database(self.test_dir)
        cur = self.conn.cursor()
        for path, parent in [
            ("/a/foo", "/a"),
            ("/a/foo/sub", "/a/foo"),
            ("/a/foobar", "/a"),
        ]:
            cur.execute(
                "INSERT INTO directories (path, parent_path, mtime) VALUES (?, ?, 0)",
                (path, parent),
            )
        for directory, name in [
            ("/a/foo", "f1"),
            ("/a/foo/sub", "f2"),
            ("/a/foobar", "f3"),
        ]:
            cur.execute(
                "INSERT INTO files (directory_path, name, size, mtime) VALUES (?, ?, 0, 0)",
                (directory, name),
            )
        self.conn.commit()

    def tearDown(self):
        close_database(self.conn)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _dirs(self):
        return {r[0] for r in self.conn.execute("SELECT path FROM directories")}

    def _file_dirs(self):
        return {r[0] for r in self.conn.execute("SELECT directory_path FROM files")}

    def test_delete_directory_does_not_remove_sibling_prefix(self):
        update_index_after_change(self.conn, "delete_directory", Path("/a/foo"))
        self.assertNotIn("/a/foo", self._dirs())
        self.assertNotIn("/a/foo/sub", self._dirs())
        self.assertIn("/a/foobar", self._dirs())  # must survive
        self.assertIn("/a/foobar", self._file_dirs())
        self.assertNotIn("/a/foo", self._file_dirs())
        self.assertNotIn("/a/foo/sub", self._file_dirs())

    def test_delete_directory_escapes_like_wildcards(self):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO directories (path, parent_path, mtime) VALUES ('/a/te_st/sub', '/a/te_st', 0)"
        )
        cur.execute(
            "INSERT INTO directories (path, parent_path, mtime) VALUES ('/a/teXst/sub', '/a/teXst', 0)"
        )
        self.conn.commit()
        update_index_after_change(self.conn, "delete_directory", Path("/a/te_st"))
        dirs = self._dirs()
        self.assertNotIn("/a/te_st/sub", dirs)
        self.assertIn("/a/teXst/sub", dirs)  # '_' must not act as a wildcard


class TestIndexerStatGuard(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.conn = initialize_database(self.test_dir)

    def tearDown(self):
        close_database(self.conn)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_add_file_on_missing_path_does_not_raise(self):
        missing = Path(self.test_dir) / "ghost.txt"
        # Must not raise even though the file does not exist.
        update_index_after_change(self.conn, "add_file", missing)

    def test_add_directory_on_missing_path_does_not_raise(self):
        missing = Path(self.test_dir) / "ghost_dir"
        # Must not raise even though the directory does not exist.
        update_index_after_change(self.conn, "add_directory", missing)


class TestInitializeDatabaseDefensive(unittest.TestCase):
    def test_unusable_db_path_raises_pystou_error(self):
        test_dir = tempfile.mkdtemp()
        try:
            # Make the db path a directory so sqlite cannot open it as a file.
            os.mkdir(os.path.join(test_dir, "filesystem_index.db"))
            with self.assertRaises(PystouError):
                initialize_database(test_dir)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
