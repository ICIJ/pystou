# tests/test_fs_walker.py
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import common.fs_walker as fs_walker
from common.fs_walker import collect_directories, is_excluded_dir
from common.indexer import (
    close_database,
    initialize_database,
    load_directories_from_index,
)


class TestDeepTree(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.conn = initialize_database(self.test_dir)
        self._recursion_limit = sys.getrecursionlimit()

    def tearDown(self):
        close_database(self.conn)
        # shutil.rmtree recurses on deep trees; raise the limit for cleanup.
        sys.setrecursionlimit(self._recursion_limit + 5000)
        try:
            shutil.rmtree(self.test_dir, ignore_errors=True)
        finally:
            sys.setrecursionlimit(self._recursion_limit)

    def test_deep_tree_does_not_raise_recursion_error(self):
        # Build a tree deeper than the default recursion limit.
        depth = sys.getrecursionlimit() + 200
        deep = Path(self.test_dir)
        for _ in range(depth):
            deep = deep / "d"
        # os.makedirs recurses internally, so raise the limit just for directory creation.
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(depth + 2000)
        try:
            os.makedirs(deep)
        finally:
            sys.setrecursionlimit(old_limit)
        # Must complete without RecursionError.
        fs_walker.collect_directories(self.conn, self.test_dir, recursive=True)
        count = self.conn.execute("SELECT COUNT(*) FROM directories").fetchone()[0]
        self.assertEqual(count, depth)


class FakeEntry:
    def __init__(self, path, name, is_dir, raise_stat=False):
        self.path = path
        self.name = name
        self._is_dir = is_dir
        self._raise_stat = raise_stat

    def is_dir(self, follow_symlinks=True):
        return self._is_dir

    def is_file(self, follow_symlinks=True):
        return not self._is_dir

    def stat(self, follow_symlinks=True):
        if self._raise_stat:
            raise OSError("simulated stat failure")

        class _S:
            st_mtime = 0.0
            st_size = 0

        return _S()


class TestBadEntryIsolation(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.conn = initialize_database(self.test_dir)

    def tearDown(self):
        close_database(self.conn)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_bad_entry_does_not_abort_siblings(self):
        bad = FakeEntry("/x/bad", "bad", is_dir=False, raise_stat=True)
        good = FakeEntry("/x/good", "good", is_dir=False, raise_stat=False)

        @contextmanager
        def fake_scandir(_path):
            yield [bad, good]

        with patch.object(fs_walker.os, "scandir", fake_scandir):
            fs_walker.collect_directories(self.conn, "/x", recursive=False)

        names = {r[0] for r in self.conn.execute("SELECT name FROM files")}
        self.assertIn("good", names)  # sibling survived the bad entry
        self.assertNotIn("bad", names)


class TestExcludeTrash(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_is_excluded_dir(self):
        self.assertTrue(is_excluded_dir(".pystou-trash"))
        self.assertFalse(is_excluded_dir("data"))

    def test_scan_skips_trash(self):
        root = Path(self.test_dir)
        (root / "keep").mkdir()
        (root / ".pystou-trash" / "20260613T000000Z-aaaa" / "0" / "victim").mkdir(parents=True)
        conn = initialize_database(self.test_dir)
        collect_directories(conn, str(root), recursive=True)
        paths = [str(p) for p in load_directories_from_index(conn)]
        conn.close()
        self.assertTrue(any(p.endswith("keep") for p in paths))
        self.assertFalse(any(".pystou-trash" in p for p in paths))


class TestProgressCallback(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_progress_cb_invoked(self):
        from common.fs_walker import collect_directories
        from common.indexer import initialize_database

        (Path(self.test_dir) / "a").mkdir()
        (Path(self.test_dir) / "a" / "f.txt").write_text("x")
        calls = []
        conn = initialize_database(self.test_dir)
        collect_directories(
            conn, self.test_dir, recursive=True, progress_cb=lambda d, f: calls.append((d, f))
        )
        conn.close()
        self.assertTrue(calls)  # callback received (dirs, files) counts


if __name__ == "__main__":
    unittest.main()
