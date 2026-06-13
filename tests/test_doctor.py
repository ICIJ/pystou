import unittest
from types import SimpleNamespace
from unittest.mock import patch

from doctor.main import (
    ToolStatus,
    _tool_version,
    check_environment,
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


class TestToolVersion(unittest.TestCase):
    """_tool_version extracts a clean version number across tools."""

    def _fake_run(self, stdout="", stderr=""):
        def run(cmd, *args, **kwargs):
            self.last_cmd = cmd
            return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=0)

        return run

    def test_zstd_banner_is_cleaned(self):
        out = "*** Zstandard CLI (64-bit) v1.5.5, by Yann Collet ***\n"
        with patch("doctor.main.subprocess.run", side_effect=self._fake_run(stdout=out)):
            self.assertEqual(_tool_version("zstd"), "1.5.5")

    def test_7z_banner_cleaned_and_uses_bare_command(self):
        # 7z has no --version flag; the bare command prints a banner with the version.
        out = "7-Zip [64] 16.02 : Copyright (c) 1999-2016 Igor Pavlov\n"
        with patch("doctor.main.subprocess.run", side_effect=self._fake_run(stdout=out)):
            self.assertEqual(_tool_version("7z"), "16.02")
        self.assertEqual(self.last_cmd, ["7z"])  # not ["7z", "--version"]

    def test_readpst_version_number(self):
        out = "ReadPST / LibPST v0.6.76\n"
        with patch("doctor.main.subprocess.run", side_effect=self._fake_run(stdout=out)):
            self.assertEqual(_tool_version("readpst"), "0.6.76")

    def test_falls_back_to_first_line_without_number(self):
        out = "some tool with no version number\n"
        with patch("doctor.main.subprocess.run", side_effect=self._fake_run(stdout=out)):
            self.assertEqual(_tool_version("mystery"), "some tool with no version number")


if __name__ == "__main__":
    unittest.main()
