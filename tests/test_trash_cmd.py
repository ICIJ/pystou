# tests/test_trash_cmd.py
import argparse
import shutil
import tempfile
import unittest
from pathlib import Path

from common import trash
from trash.main import add_trash_arguments
from trash.main import main as trash_main


class TestTrashCommand(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _args(self, sub, **kw):
        parser = argparse.ArgumentParser()
        add_trash_arguments(parser)
        ns = parser.parse_args([sub, self.test_dir])
        for k, v in kw.items():
            setattr(ns, k, v)
        return ns

    def test_purge_all_empties_trash(self):
        victim = Path(self.test_dir) / "f.txt"
        victim.write_text("x")
        trash.quarantine([victim], self.test_dir, operation="cleanup", command="c")
        trash_main(self._args("purge", all=True, run=None, older_than=None, log_dir=self.test_dir))
        self.assertEqual(trash.list_runs(self.test_dir), [])


if __name__ == "__main__":
    unittest.main()
