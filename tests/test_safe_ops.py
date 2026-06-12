# tests/test_safe_ops.py
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from common.safe_ops import (
    make_unique_dir,
    reserve_unique_file,
    unique_path,
    verify_then_delete,
)


class TestUniquePath(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_returns_base_when_free(self):
        base = Path(self.test_dir) / "out"
        self.assertEqual(unique_path(base), base)

    def test_appends_counter_on_collision(self):
        base = Path(self.test_dir) / "out"
        base.mkdir()
        result = unique_path(base)
        self.assertEqual(result, Path(f"{base} (1)"))


class TestVerifyThenDelete(unittest.TestCase):
    def test_keeps_when_extraction_failed(self):
        calls = []
        verify_then_delete(Path("/tmp/a.zip"), success=False, delete_fn=lambda: calls.append(1))
        self.assertEqual(calls, [])  # delete_fn not invoked

    def test_deletes_when_extraction_succeeded(self):
        calls = []
        verify_then_delete(Path("/tmp/a.zip"), success=True, delete_fn=lambda: calls.append(1))
        self.assertEqual(calls, [1])


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


if __name__ == "__main__":
    unittest.main()
