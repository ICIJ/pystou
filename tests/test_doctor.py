import unittest
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


if __name__ == "__main__":
    unittest.main()
