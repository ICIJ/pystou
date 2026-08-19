# tests/test_logger.py
import logging
import shutil
import tempfile
import unittest

from common.logger import setup_logging


class TestLogger(unittest.TestCase):
    def setUp(self):
        self.log_dir = tempfile.mkdtemp()

    def tearDown(self):
        root = logging.getLogger()
        for h in root.handlers[:]:
            root.removeHandler(h)
            h.close()
        shutil.rmtree(self.log_dir, ignore_errors=True)

    def test_setup_logging_is_idempotent(self):
        setup_logging("x", self.log_dir)
        setup_logging("x", self.log_dir)
        self.assertEqual(len(logging.getLogger().handlers), 1)


if __name__ == "__main__":
    unittest.main()
