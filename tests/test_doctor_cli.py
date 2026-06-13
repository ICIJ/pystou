import json
import unittest
from unittest import mock

import typer
from typer.testing import CliRunner

from doctor.main import ToolStatus, doctor_command

ALL_OK = [
    ToolStatus("readpst", True, "v1", "PST", "hint"),
    ToolStatus("7z", True, "v2", "zip", "hint"),
    ToolStatus("zstd", True, "v3", "zst", "hint"),
]

ONE_MISSING = [
    ToolStatus("readpst", True, "v1", "PST", "hint"),
    ToolStatus("7z", False, None, "zip", "install p7zip"),
    ToolStatus("zstd", True, "v3", "zst", "hint"),
]


def _app():
    app = typer.Typer()
    app.command()(doctor_command)
    return app


class TestDoctorCommand(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_exit_zero_when_all_present(self):
        """Exit code is 0 when all tools are available."""
        with mock.patch("doctor.main.check_environment", return_value=ALL_OK):
            r = self.runner.invoke(_app(), [])
        self.assertEqual(r.exit_code, 0)

    def test_exit_one_when_missing(self):
        """Exit code is 1 when any tool is missing."""
        with mock.patch("doctor.main.check_environment", return_value=ONE_MISSING):
            r = self.runner.invoke(_app(), [])
        self.assertEqual(r.exit_code, 1)

    def test_json_parses(self):
        """--json outputs a parseable JSON list of 3 dicts without ANSI codes."""
        with mock.patch("doctor.main.check_environment", return_value=ALL_OK):
            r = self.runner.invoke(_app(), ["--json"])
        self.assertEqual(r.exit_code, 0)
        self.assertNotIn("\x1b[", r.output)
        data = json.loads(r.output)
        self.assertEqual(len(data), 3)
        for entry in data:
            self.assertEqual(
                set(entry.keys()),
                {"name", "available", "version", "enables", "install_hint"},
            )


if __name__ == "__main__":
    unittest.main()
