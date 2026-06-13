# tests/test_errors.py
import unittest

from common.errors import (
    CrossDeviceTrashError,
    InvalidDirectoryError,
    PystouError,
    TrashUnavailableError,
)


class TestErrors(unittest.TestCase):
    def test_invalid_directory_is_pystou_error(self):
        self.assertTrue(issubclass(InvalidDirectoryError, PystouError))

    def test_pystou_error_is_exception(self):
        self.assertTrue(issubclass(PystouError, Exception))

    def test_message_preserved(self):
        err = InvalidDirectoryError("bad path")
        self.assertEqual(str(err), "bad path")


class TestTrashErrors(unittest.TestCase):
    def test_cross_device_is_pystou_error(self):
        self.assertTrue(issubclass(CrossDeviceTrashError, PystouError))

    def test_trash_unavailable_is_pystou_error(self):
        self.assertTrue(issubclass(TrashUnavailableError, PystouError))


if __name__ == "__main__":
    unittest.main()
