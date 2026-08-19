# tests/test_xdg_paths_cli.py
import logging
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import typer
from typer.testing import CliRunner

from dedup_folders.main import dedup_command
from extract.main import extract_command
from restore.main import restore_command


class TestCommandsWriteNothingIntoTheCurrentDirectory(unittest.TestCase):
    """No subcommand may drop logs or an index into the user's working directory."""

    def setUp(self):
        self.cwd = tempfile.mkdtemp()
        self.target = tempfile.mkdtemp()
        self.state = tempfile.mkdtemp()
        self.cache = tempfile.mkdtemp()
        Path(self.target, "a").mkdir()
        self.origin = os.getcwd()
        os.chdir(self.cwd)

    def tearDown(self):
        os.chdir(self.origin)
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            handler.close()
        for path in (self.cwd, self.target, self.state, self.cache):
            shutil.rmtree(path, ignore_errors=True)

    def _run(self, command, *args):
        app = typer.Typer()
        app.command()(command)
        with mock.patch.dict(
            os.environ, {"XDG_STATE_HOME": self.state, "XDG_CACHE_HOME": self.cache}
        ):
            return CliRunner().invoke(app, [self.target, *args])

    def _cwd_entries(self):
        return sorted(os.listdir(self.cwd))

    def test_dedup_leaves_the_working_directory_clean(self):
        result = self._run(dedup_command, "--action", "skip")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self._cwd_entries(), [])

    def test_extract_leaves_the_working_directory_clean(self):
        result = self._run(extract_command)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self._cwd_entries(), [])

    def test_restore_leaves_the_working_directory_clean(self):
        result = self._run(restore_command, "--all")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self._cwd_entries(), [])

    def test_logs_land_in_the_xdg_state_directory(self):
        self._run(dedup_command, "--action", "skip")
        logs = list(Path(self.state, "pystou/logs").glob("dedup_folders.*.log"))
        self.assertEqual(len(logs), 1)

    def test_the_index_lands_in_the_xdg_cache_directory(self):
        self._run(dedup_command, "--action", "skip")
        self.assertEqual(len(list(Path(self.cache, "pystou/index").glob("*.db"))), 1)


if __name__ == "__main__":
    unittest.main()
