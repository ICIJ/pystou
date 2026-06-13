import argparse
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from doctor.main import (
    ToolStatus,
    _tool_version,
    check_environment,
    main,
)


class TestCheckEnvironment(unittest.TestCase):
    """Tests for the pure check_environment core."""

    def test_all_available(self):
        """When every tool is present, all three statuses are available."""
        with (
            patch("doctor.main.shutil.which", return_value="/usr/bin/x"),
            patch("doctor.main._tool_version", return_value="v1"),
        ):
            statuses = check_environment()

        self.assertEqual(len(statuses), 3)
        for status in statuses:
            self.assertIsInstance(status, ToolStatus)
            self.assertTrue(status.available)

    def test_missing_readpst(self):
        """When readpst is absent, its status is unavailable with an install hint."""

        def fake_which(name):
            return None if name == "readpst" else "/usr/bin/x"

        with (
            patch("doctor.main.shutil.which", side_effect=fake_which),
            patch("doctor.main._tool_version", return_value="v1"),
        ):
            statuses = check_environment()

        readpst = next(s for s in statuses if s.name == "readpst")
        self.assertFalse(readpst.available)
        self.assertTrue(readpst.install_hint)

    def test_zstd_via_module_only(self):
        """zstd counts as available when only the Python module is present."""

        def fake_which(name):
            return None if name == "zstd" else "/usr/bin/x"

        with (
            patch("doctor.main.shutil.which", side_effect=fake_which),
            patch("doctor.main._zstandard_module_available", return_value=True),
            patch("doctor.main._tool_version", return_value="v1"),
        ):
            statuses = check_environment()

        zstd = next(s for s in statuses if s.name == "zstd")
        self.assertTrue(zstd.available)
        self.assertEqual(zstd.version, "python zstandard module")

    def test_version_never_raises(self):
        """_tool_version returns None instead of propagating errors."""
        with patch("doctor.main.subprocess.run", side_effect=OSError("boom")):
            self.assertIsNone(_tool_version("anything"))


class TestMain(unittest.TestCase):
    """Tests for the main entry point exit codes and output."""

    def _all_available(self):
        return [
            ToolStatus("readpst", True, "v1", "PST archives", "hint"),
            ToolStatus("7z", True, "v1", "split ZIP archives", "hint"),
            ToolStatus("zstd", True, "v1", "Zstandard archives", "hint"),
        ]

    def _one_missing(self):
        statuses = self._all_available()
        statuses[0] = ToolStatus("readpst", False, None, "PST archives", "hint")
        return statuses

    def test_main_exit_zero_when_all_present(self):
        """main returns 0 when every capability is available."""
        with (
            patch("doctor.main.check_environment", return_value=self._all_available()),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(argparse.Namespace(json=False)), 0)

    def test_main_exit_one_when_missing(self):
        """main returns 1 when a capability is missing."""
        with (
            patch("doctor.main.check_environment", return_value=self._one_missing()),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(argparse.Namespace(json=False)), 1)

    def test_json_output(self):
        """--json prints a parseable array with the expected keys."""
        buffer = io.StringIO()
        with (
            patch("doctor.main.check_environment", return_value=self._all_available()),
            contextlib.redirect_stdout(buffer),
        ):
            main(argparse.Namespace(json=True))

        data = json.loads(buffer.getvalue())
        self.assertEqual(len(data), 3)
        for entry in data:
            self.assertEqual(
                set(entry.keys()),
                {"name", "available", "version", "enables", "install_hint"},
            )


if __name__ == "__main__":
    unittest.main()
