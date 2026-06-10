# tests/test_safe_extract.py
import shutil
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from common.safe_extract import safe_extract_tar, safe_extract_zip


class TestSafeExtractZip(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.dest = Path(self.test_dir) / "out"
        self.dest.mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_happy_path_extracts(self):
        zip_path = Path(self.test_dir) / "ok.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("inner.txt", "hello")
        with zipfile.ZipFile(zip_path, "r") as zf:
            self.assertTrue(safe_extract_zip(zf, self.dest))
        self.assertTrue((self.dest / "inner.txt").exists())

    def test_traversal_member_is_rejected(self):
        zip_path = Path(self.test_dir) / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../escaped.txt", "pwned")
        with zipfile.ZipFile(zip_path, "r") as zf:
            self.assertFalse(safe_extract_zip(zf, self.dest))
        escaped = Path(self.test_dir) / "escaped.txt"
        self.assertFalse(escaped.exists())  # nothing written outside dest


class TestSafeExtractTar(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.dest = Path(self.test_dir) / "out"
        self.dest.mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_happy_path_extracts(self):
        src = Path(self.test_dir) / "inner.txt"
        src.write_text("hi")
        tar_path = Path(self.test_dir) / "ok.tar"
        with tarfile.open(tar_path, "w") as tf:
            tf.add(src, arcname="inner.txt")
        with tarfile.open(tar_path, "r") as tf:
            self.assertTrue(safe_extract_tar(tf, self.dest))
        self.assertTrue((self.dest / "inner.txt").exists())

    def test_traversal_member_is_rejected(self):
        tar_path = Path(self.test_dir) / "evil.tar"
        payload = Path(self.test_dir) / "payload"
        payload.write_text("x")
        with tarfile.open(tar_path, "w") as tf:
            tf.add(payload, arcname="../escaped.txt")
        with tarfile.open(tar_path, "r") as tf:
            self.assertFalse(safe_extract_tar(tf, self.dest))
        self.assertFalse((Path(self.test_dir) / "escaped.txt").exists())

    def test_symlink_member_is_rejected(self):
        tar_path = Path(self.test_dir) / "link.tar"
        with tarfile.open(tar_path, "w") as tf:
            info = tarfile.TarInfo("link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tf.addfile(info)
        with tarfile.open(tar_path, "r") as tf:
            self.assertFalse(safe_extract_tar(tf, self.dest))
        self.assertFalse((self.dest / "link").exists())

    def test_hardlink_member_is_rejected(self):
        tar_path = Path(self.test_dir) / "hard.tar"
        with tarfile.open(tar_path, "w") as tf:
            info = tarfile.TarInfo("hl")
            info.type = tarfile.LNKTYPE
            info.linkname = "inner.txt"
            tf.addfile(info)
        with tarfile.open(tar_path, "r") as tf:
            self.assertFalse(safe_extract_tar(tf, self.dest))
        self.assertFalse((self.dest / "hl").exists())

    def test_device_member_is_rejected(self):
        tar_path = Path(self.test_dir) / "dev.tar"
        with tarfile.open(tar_path, "w") as tf:
            info = tarfile.TarInfo("dev")
            info.type = tarfile.BLKTYPE
            info.devmajor = 1
            info.devminor = 3
            tf.addfile(info)
        with tarfile.open(tar_path, "r") as tf:
            self.assertFalse(safe_extract_tar(tf, self.dest))
        self.assertFalse((self.dest / "dev").exists())

    def test_nested_traversal_member_is_rejected(self):
        tar_path = Path(self.test_dir) / "nested.tar"
        payload = Path(self.test_dir) / "payload"
        payload.write_text("x")
        with tarfile.open(tar_path, "w") as tf:
            tf.add(payload, arcname="sub/../../escaped.txt")
        with tarfile.open(tar_path, "r") as tf:
            self.assertFalse(safe_extract_tar(tf, self.dest))
        self.assertFalse((Path(self.test_dir) / "escaped.txt").exists())


class TestSafeExtractZipAbsolute(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.dest = Path(self.test_dir) / "out"
        self.dest.mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_absolute_member_is_rejected(self):
        zip_path = Path(self.test_dir) / "abs.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("/etc/cron.d/evil", "pwned")
        with zipfile.ZipFile(zip_path, "r") as zf:
            self.assertFalse(safe_extract_zip(zf, self.dest))


if __name__ == "__main__":
    unittest.main()
