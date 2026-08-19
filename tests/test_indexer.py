# tests/test_indexer.py
import os
import shutil
import sqlite3
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from common.errors import PystouError
from common.indexer import (
    close_database,
    index_db_path,
    index_has_data,
    initialize_database,
    open_or_rescan,
    update_index_after_change,
)


def _indexed_names(conn) -> set:
    return {Path(row[0]).name for row in conn.execute("SELECT path FROM directories")}


def _size_and_count(conn, directory) -> tuple:
    return conn.execute(
        "SELECT COALESCE(SUM(size), 0), COUNT(*) FROM files WHERE directory_path = ?",
        (str(directory),),
    ).fetchone()


class TestIndexerDeleteDirectory(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.conn = initialize_database(os.path.join(self.test_dir, "index.db"))
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
        self.conn = initialize_database(os.path.join(self.test_dir, "index.db"))

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
            db_path = os.path.join(test_dir, "index.db")
            os.mkdir(db_path)
            with self.assertRaises(PystouError):
                initialize_database(db_path)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)


class TestIndexHasData(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.conn = initialize_database(os.path.join(self.test_dir, "index.db"))

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
        self.conn = initialize_database(os.path.join(self.test_dir, "index.db"))

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
        self.db_path = os.path.join(self.test_dir, "index.db")
        legacy = sqlite3.connect(self.db_path)
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
        conn = initialize_database(self.db_path)
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


class TestOpenOrRescan(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        Path(self.test_dir, "a").mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _open(self, answer=None):
        with unittest.mock.patch("common.console.confirm", return_value=answer) as confirm:
            conn = open_or_rescan(self.test_dir, self.test_dir, recursive=True)
        return conn, confirm

    def test_missing_index_scans_without_prompting(self):
        conn, confirm = self._open()
        try:
            self.assertTrue(index_has_data(conn))
            confirm.assert_not_called()
        finally:
            close_database(conn)

    def test_populated_index_is_kept_when_accepted(self):
        close_database(self._open()[0])
        Path(self.test_dir, "b").mkdir()
        conn, _ = self._open(answer=True)
        try:
            self.assertEqual(_indexed_names(conn), {"a"})
        finally:
            close_database(conn)

    def test_populated_index_is_rescanned_when_declined(self):
        close_database(self._open()[0])
        Path(self.test_dir, "b").mkdir()
        conn, _ = self._open(answer=False)
        try:
            self.assertEqual(_indexed_names(conn), {"a", "b"})
        finally:
            close_database(conn)


class TestIndexDbPath(unittest.TestCase):
    def setUp(self):
        self.db_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.db_dir, ignore_errors=True)

    def test_same_target_always_resolves_to_the_same_file(self):
        first = index_db_path(self.db_dir, "/data/photos")
        second = index_db_path(self.db_dir, "/data/photos/")
        self.assertEqual(first, second)

    def test_different_targets_resolve_to_different_files(self):
        self.assertNotEqual(
            index_db_path(self.db_dir, "/data/photos"),
            index_db_path(self.db_dir, "/data/music"),
        )

    def test_targets_sharing_a_basename_resolve_to_different_files(self):
        self.assertNotEqual(
            index_db_path(self.db_dir, "/alpha/data"),
            index_db_path(self.db_dir, "/beta/data"),
        )

    def test_relative_and_absolute_targets_agree(self):
        target = Path(self.db_dir).name
        with unittest.mock.patch("os.getcwd", return_value=str(Path(self.db_dir).parent)):
            self.assertEqual(
                index_db_path(self.db_dir, target),
                index_db_path(self.db_dir, self.db_dir),
            )

    def test_the_name_is_recognisable_and_lands_in_the_db_dir(self):
        path = Path(index_db_path(self.db_dir, "/data/photos"))
        self.assertEqual(path.parent, Path(self.db_dir))
        self.assertTrue(path.name.startswith("photos-"))
        self.assertTrue(path.name.endswith(".db"))
