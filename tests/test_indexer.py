# tests/test_indexer.py
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from common.errors import PystouError
from common.indexer import (
    close_database,
    index_has_data,
    initialize_database,
    update_index_after_change,
)


def _size_and_count(conn, directory) -> tuple:
    return conn.execute(
        "SELECT COALESCE(SUM(size), 0), COUNT(*) FROM files WHERE directory_path = ?",
        (str(directory),),
    ).fetchone()


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


class TestIndexHasData(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.conn = initialize_database(self.test_dir)

    def tearDown(self):
        close_database(self.conn)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_freshly_initialized_index_has_no_data(self):
        self.assertFalse(index_has_data(self.conn))

    def test_index_with_directory_row_has_data(self):
        self.conn.execute(
            "INSERT INTO directories (path, parent_path, mtime) VALUES ('/a', '/', 0)"
        )
        self.conn.commit()
        self.assertTrue(index_has_data(self.conn))


class TestFilesAreIndexedOnce(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.conn = initialize_database(self.test_dir)

    def tearDown(self):
        close_database(self.conn)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_repeated_add_file_does_not_inflate_size(self):
        path = Path(self.test_dir) / "f.txt"
        path.write_text("0123456789")
        for _ in range(3):
            update_index_after_change(self.conn, "add_file", path)
        self.assertEqual(_size_and_count(self.conn, self.test_dir), (10, 1))


class TestLegacyIndexRetrofit(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        legacy = sqlite3.connect(os.path.join(self.test_dir, "filesystem_index.db"))
        legacy.execute(
            "CREATE TABLE files (id INTEGER PRIMARY KEY, directory_path TEXT, name TEXT,"
            " size INTEGER, mtime REAL)"
        )
        for _ in range(3):
            legacy.execute(
                "INSERT INTO files (directory_path, name, size, mtime)"
                " VALUES ('/a', 'f.txt', 10, 0)"
            )
        legacy.commit()
        legacy.close()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_existing_duplicate_rows_are_collapsed(self):
        conn = initialize_database(self.test_dir)
        try:
            self.assertEqual(_size_and_count(conn, "/a"), (10, 1))
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO files (directory_path, name, size, mtime)"
                    " VALUES ('/a', 'f.txt', 10, 0)"
                )
        finally:
            close_database(conn)


if __name__ == "__main__":
    unittest.main()
