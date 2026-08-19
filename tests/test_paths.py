# tests/test_paths.py
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from common import paths


class TestXdgDefaults(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def _without_xdg(self):
        return mock.patch.dict(os.environ, {"HOME": self.home}, clear=True)

    def test_log_dir_falls_back_to_local_state(self):
        with self._without_xdg():
            self.assertEqual(paths.log_dir(), Path(self.home, ".local/state/pystou/logs"))

    def test_rename_dir_falls_back_to_local_state(self):
        with self._without_xdg():
            self.assertEqual(paths.rename_dir(), Path(self.home, ".local/state/pystou/renames"))

    def test_index_dir_falls_back_to_cache(self):
        with self._without_xdg():
            self.assertEqual(paths.index_dir(), Path(self.home, ".cache/pystou/index"))

    def test_relative_xdg_value_is_ignored(self):
        """The spec requires relative XDG_* values to be treated as unset."""
        with mock.patch.dict(
            os.environ,
            {"HOME": self.home, "XDG_STATE_HOME": "rel/state", "XDG_CACHE_HOME": "rel/cache"},
            clear=True,
        ):
            self.assertEqual(paths.log_dir(), Path(self.home, ".local/state/pystou/logs"))
            self.assertEqual(paths.index_dir(), Path(self.home, ".cache/pystou/index"))


class TestXdgOverrides(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_log_dir_honors_xdg_state_home(self):
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.root}):
            self.assertEqual(paths.log_dir(), Path(self.root, "pystou/logs"))

    def test_rename_dir_honors_xdg_state_home(self):
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.root}):
            self.assertEqual(paths.rename_dir(), Path(self.root, "pystou/renames"))
            self.assertTrue(paths.rename_dir().is_dir())

    def test_index_dir_honors_xdg_cache_home(self):
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": self.root}):
            self.assertEqual(paths.index_dir(), Path(self.root, "pystou/index"))

    def test_resolved_directories_are_created(self):
        with mock.patch.dict(
            os.environ, {"XDG_STATE_HOME": self.root, "XDG_CACHE_HOME": self.root}
        ):
            self.assertTrue(paths.log_dir().is_dir())
            self.assertTrue(paths.index_dir().is_dir())


if __name__ == "__main__":
    unittest.main()
