# tests/test_logger.py
import logging
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_an_omitted_log_dir_writes_under_the_xdg_state_directory(self):
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.log_dir}):
            setup_logging("x")
        self.assertEqual(len(list(Path(self.log_dir, "pystou/logs").glob("x.*.log"))), 1)


if __name__ == "__main__":
    unittest.main()
