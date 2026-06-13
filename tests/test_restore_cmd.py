# tests/test_restore_cmd.py
import argparse
import shutil
import tempfile
import unittest
from pathlib import Path

from common import trash
from restore.main import add_restore_arguments
from restore.main import main as restore_main


class TestRestoreCommand(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _args(self, **kw):
        parser = argparse.ArgumentParser()
        add_restore_arguments(parser)
        ns = parser.parse_args([self.test_dir])
        for k, v in kw.items():
            setattr(ns, k, v)
        return ns

    def test_restore_all_round_trip(self):
        victim = Path(self.test_dir) / "f.txt"
        victim.write_text("data")
        trash.quarantine([victim], self.test_dir, operation="cleanup", command="c")
        self.assertFalse(victim.exists())
        restore_main(
            self._args(all=True, run=None, path=None, log_dir=self.test_dir, db_dir=self.test_dir)
        )
        self.assertTrue(victim.is_file())


if __name__ == "__main__":
    unittest.main()
