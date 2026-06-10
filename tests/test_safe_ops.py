# tests/test_safe_ops.py
import tempfile
import shutil
import unittest
from pathlib import Path

from common.safe_ops import unique_path, verify_then_delete


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
        verify_then_delete(
            Path("/tmp/a.zip"), success=False, delete_fn=lambda: calls.append(1)
        )
        self.assertEqual(calls, [])  # delete_fn not invoked

    def test_deletes_when_extraction_succeeded(self):
        calls = []
        verify_then_delete(
            Path("/tmp/a.zip"), success=True, delete_fn=lambda: calls.append(1)
        )
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
