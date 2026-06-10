# tests/test_utils_extract.py
import os
import tarfile
import tempfile
import shutil
import unittest
import zipfile
from pathlib import Path

import common.utils as utils


class TestExtractArchiveSafety(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_traversal_zip_is_not_extracted_outside(self):
        zip_path = Path(self.test_dir) / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../escaped.txt", "pwned")
        result = utils.extract_archive(zip_path)
        self.assertFalse(result)
        self.assertFalse((Path(self.test_dir).parent / "escaped.txt").exists())

    def test_zst_decompress_does_not_clobber_existing_output(self):
        zstd = self._import_zstd_or_skip()
        # Create plain.txt.zst whose decompressed target plain.txt already exists.
        data = b"new-content"
        src = Path(self.test_dir) / "plain.txt.zst"
        with open(src, "wb") as f:
            f.write(zstd.ZstdCompressor().compress(data))
        existing = Path(self.test_dir) / "plain.txt"
        existing.write_text("original")
        self.assertTrue(utils.extract_archive(src))
        # Original must be preserved; decompressed output went to a unique path.
        self.assertEqual(existing.read_text(), "original")

    def _import_zstd_or_skip(self):
        try:
            import zstandard as zstd
            return zstd
        except ImportError:
            self.skipTest("zstandard module not installed")


if __name__ == "__main__":
    unittest.main()
