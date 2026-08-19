# tests/test_safe_ops.py
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from common.safe_ops import make_unique_dir, reserve_unique_file, reserve_unique_name


class TestMakeUniqueDir(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_creates_base_when_free(self):
        base = Path(self.test_dir) / "out"
        result = make_unique_dir(base)
        self.assertEqual(result, base)
        self.assertTrue(base.is_dir())

    def test_appends_counter_when_dir_exists(self):
        base = Path(self.test_dir) / "out"
        base.mkdir()
        result = make_unique_dir(base)
        self.assertEqual(result, Path(f"{base} (1)"))
        self.assertTrue(result.is_dir())

    def test_appends_counter_when_file_exists(self):
        base = Path(self.test_dir) / "out"
        base.write_text("i am a file")  # cross-type collision
        result = make_unique_dir(base)
        self.assertEqual(result, Path(f"{base} (1)"))
        self.assertTrue(result.is_dir())

    def test_concurrent_calls_get_distinct_dirs(self):
        base = Path(self.test_dir) / "out"
        results = []
        lock = threading.Lock()

        def worker():
            p = make_unique_dir(base)
            with lock:
                results.append(p)

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 16)
        self.assertEqual(len(set(results)), 16)  # all distinct
        for p in results:
            self.assertTrue(p.is_dir())


class TestReserveUniqueFile(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_creates_base_when_free(self):
        base = Path(self.test_dir) / "out"
        result = reserve_unique_file(base)
        self.assertEqual(result, base)
        self.assertTrue(base.is_file())

    def test_appends_counter_when_file_exists(self):
        base = Path(self.test_dir) / "out"
        base.write_text("x")
        result = reserve_unique_file(base)
        self.assertEqual(result, Path(f"{base} (1)"))
        self.assertTrue(result.is_file())

    def test_appends_counter_when_dir_exists(self):
        base = Path(self.test_dir) / "out"
        base.mkdir()  # cross-type collision
        result = reserve_unique_file(base)
        self.assertEqual(result, Path(f"{base} (1)"))
        self.assertTrue(result.is_file())

    def test_concurrent_calls_get_distinct_files(self):
        base = Path(self.test_dir) / "out"
        results = []
        lock = threading.Lock()

        def worker():
            p = reserve_unique_file(base)
            with lock:
                results.append(p)

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 16)
        self.assertEqual(len(set(results)), 16)
        for p in results:
            self.assertTrue(p.is_file())


class TestReserveUniqueName(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_returns_path_inside_fresh_empty_holding_dir(self):
        dest = Path(self.test_dir)
        reserved = reserve_unique_name(dest, "report.pdf")
        self.assertEqual(reserved.name, "report.pdf")
        self.assertTrue(reserved.parent.is_dir())
        self.assertEqual(list(reserved.parent.iterdir()), [])  # empty, ready for rename

    def test_two_same_basenames_get_distinct_holding_dirs(self):
        dest = Path(self.test_dir)
        a = reserve_unique_name(dest, "report.pdf")
        b = reserve_unique_name(dest, "report.pdf")
        self.assertNotEqual(a.parent, b.parent)
        self.assertEqual(a.name, b.name)

    def test_rename_a_directory_into_reservation(self):
        src = Path(self.test_dir) / "srcdir"
        (src / "inner").mkdir(parents=True)
        reserved = reserve_unique_name(Path(self.test_dir), "srcdir")
        os.rename(src, reserved)
        self.assertTrue((reserved / "inner").is_dir())

    def test_concurrent_calls_get_distinct_dirs(self):
        dest = Path(self.test_dir)
        results = []
        lock = threading.Lock()

        def worker():
            p = reserve_unique_name(dest, "x")
            with lock:
                results.append(p)

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len({p.parent for p in results}), 16)


class TestKeepSuffix(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_keep_suffix_puts_counter_before_extension(self):
        base = Path(self.dir) / "note.txt"
        first = reserve_unique_file(base, keep_suffix=True)
        second = reserve_unique_file(base, keep_suffix=True)
        self.assertEqual(first.name, "note.txt")
        self.assertEqual(second.name, "note (1).txt")

    def test_default_still_suffixes_whole_name(self):
        base = Path(self.dir) / "note.txt"
        reserve_unique_file(base)
        second = reserve_unique_file(base)
        self.assertEqual(second.name, "note.txt (1)")

    def test_keep_suffix_on_extensionless_name(self):
        base = Path(self.dir) / "README"
        reserve_unique_file(base, keep_suffix=True)
        second = reserve_unique_file(base, keep_suffix=True)
        self.assertEqual(second.name, "README (1)")

    def test_make_unique_dir_accepts_keep_suffix(self):
        base = Path(self.dir) / "folder"
        make_unique_dir(base, keep_suffix=True)
        second = make_unique_dir(base, keep_suffix=True)
        self.assertEqual(second.name, "folder (1)")


if __name__ == "__main__":
    unittest.main()
