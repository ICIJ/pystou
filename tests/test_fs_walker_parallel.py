# tests/test_fs_walker_parallel.py
import gc
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import common.fs_walker as fs_walker
from common.fs_walker import DirScan, walk

THREAD_COUNTS = (1, 2, 8)


def build_tree(root: Path) -> None:
    """A tree wide and deep enough that several workers are busy at once."""
    for i in range(6):
        branch = root / f"branch{i}"
        branch.mkdir()
        (branch / "leaf.txt").write_text("x")
        for j in range(4):
            twig = branch / f"twig{j}"
            twig.mkdir()
            (twig / "note.txt").write_text("y")
    (root / "top.txt").write_text("z")


def os_walk_map(root: Path) -> dict:
    return {Path(cur): sorted(dirs + files) for cur, dirs, files in os.walk(root)}


def walk_map(root: Path, **kwargs) -> dict:
    return {scan.path: sorted(e.name for e in scan.entries) for scan in walk(root, **kwargs)}


class TestEquivalence(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        build_tree(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_matches_os_walk_at_every_thread_count(self):
        expected = os_walk_map(self.root)
        for threads in THREAD_COUNTS:
            with self.subTest(threads=threads):
                self.assertEqual(walk_map(self.root, threads=threads), expected)

    def test_root_is_yielded_first(self):
        first = next(iter(walk(self.root, threads=4)))
        self.assertEqual(first.path, self.root)

    def test_every_directory_visited_exactly_once(self):
        paths = [scan.path for scan in walk(self.root, threads=8)]
        self.assertEqual(len(paths), len(set(paths)))


class TestScope(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        build_tree(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_non_recursive_yields_only_the_root(self):
        scans = list(walk(self.root, recursive=False, threads=4))
        self.assertEqual([s.path for s in scans], [self.root])

    def test_max_depth_zero_yields_only_the_root(self):
        scans = list(walk(self.root, max_depth=0, threads=4))
        self.assertEqual([s.path for s in scans], [self.root])

    def test_max_depth_one_yields_the_root_and_its_children(self):
        paths = {s.path for s in walk(self.root, max_depth=1, threads=4)}
        self.assertEqual(paths, {self.root} | {self.root / f"branch{i}" for i in range(6)})

    def test_trash_is_never_yielded_or_descended(self):
        (self.root / ".pystou-trash" / "run" / "victim").mkdir(parents=True)
        paths = [str(s.path) for s in walk(self.root, threads=4)]
        self.assertFalse(any(".pystou-trash" in p for p in paths))

    def test_prune_stops_descent(self):
        paths = {s.path for s in walk(self.root, threads=4, prune=lambda e: e.name == "branch0")}
        self.assertIn(self.root / "branch1", paths)
        self.assertNotIn(self.root / "branch0", paths)

    def test_symlinked_directory_is_not_descended(self):
        (self.root / "loop").symlink_to(self.root, target_is_directory=True)
        paths = {s.path for s in walk(self.root, threads=4)}
        self.assertNotIn(self.root / "loop", paths)
        # The symlink is still visible to the consumer as an entry of the root.
        root_scan = next(s for s in walk(self.root, threads=4) if s.path == self.root)
        self.assertIn("loop", [e.name for e in root_scan.entries])


class TestErrors(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "readable").mkdir()
        (self.root / "readable" / "f.txt").write_text("x")
        (self.root / "denied").mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_unreadable_directory_yields_error_and_siblings_survive(self):
        # chmod 000 does not deny root in the container, so deny at the syscall.
        real_scandir = os.scandir
        denied = str(self.root / "denied")

        @contextmanager
        def fake_scandir(path):
            if str(path) == denied:
                raise PermissionError(13, "Permission denied")
            with real_scandir(path) as it:
                yield list(it)

        with patch.object(fs_walker.os, "scandir", fake_scandir):
            scans = {s.path: s for s in walk(self.root, threads=4)}

        self.assertIsInstance(scans[self.root / "denied"].error, PermissionError)
        self.assertEqual(scans[self.root / "denied"].entries, [])
        self.assertEqual([e.name for e in scans[self.root / "readable"].entries], ["f.txt"])


class TestDeepTree(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self._limit = sys.getrecursionlimit()

    def tearDown(self):
        sys.setrecursionlimit(self._limit + 5000)
        try:
            shutil.rmtree(self.root, ignore_errors=True)
        finally:
            sys.setrecursionlimit(self._limit)

    def test_deep_tree_does_not_raise_recursion_error(self):
        depth = 500
        deep = self.root
        for _ in range(depth):
            deep = deep / "d"
        os.makedirs(deep)
        self.assertEqual(len(list(walk(self.root, threads=4))), depth + 1)


class TestShutdown(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        build_tree(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_abandoning_the_walk_leaves_no_threads_behind(self):
        baseline = threading.active_count()
        scans = walk(self.root, threads=4)
        next(scans)
        scans.close()
        gc.collect()
        deadline = time.monotonic() + 5
        while threading.active_count() > baseline and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(threading.active_count(), baseline)


class TestDefaults(unittest.TestCase):
    def test_default_threads_is_bounded(self):
        self.assertGreaterEqual(fs_walker.default_threads(), 1)
        self.assertLessEqual(fs_walker.default_threads(), 32)

    def test_dirscan_reports_no_error_on_success(self):
        root = Path(tempfile.mkdtemp())
        try:
            scan = next(iter(walk(root, threads=1)))
            self.assertIsInstance(scan, DirScan)
            self.assertIsNone(scan.error)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
