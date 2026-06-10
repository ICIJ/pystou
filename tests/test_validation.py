import os
import tempfile
import shutil
import unittest
from pathlib import Path

from common.validation import validate_directory, validate_directory_or_exit
from common.errors import InvalidDirectoryError


class TestValidateDirectory(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_existing_directory_returns_path(self):
        result = validate_directory(self.test_dir)
        self.assertEqual(result, Path(self.test_dir))

    def test_nonexistent_raises(self):
        missing = os.path.join(self.test_dir, "nope")
        with self.assertRaises(InvalidDirectoryError):
            validate_directory(missing)

    def test_file_is_not_a_directory(self):
        file_path = os.path.join(self.test_dir, "f.txt")
        Path(file_path).touch()
        with self.assertRaises(InvalidDirectoryError):
            validate_directory(file_path)

    def test_symlink_to_directory_is_accepted(self):
        target = os.path.join(self.test_dir, "real")
        link = os.path.join(self.test_dir, "link")
        os.mkdir(target)
        os.symlink(target, link)
        self.assertEqual(validate_directory(link), Path(link))

    def test_or_exit_exits_on_bad_directory(self):
        missing = os.path.join(self.test_dir, "nope")
        with self.assertRaises(SystemExit) as cm:
            validate_directory_or_exit(missing)
        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
