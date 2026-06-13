import unittest
from unittest import mock

from typer.testing import CliRunner

from common.errors import PystouError
from pystou import __version__
from pystou.main import app, main


class TestApp(unittest.TestCase):
    def test_help_lists_commands(self):
        r = CliRunner().invoke(app, ["--help"])
        self.assertEqual(r.exit_code, 0)
        for cmd in (
            "cleanup",
            "dedup",
            "extract",
            "identify",
            "stats",
            "empty",
            "restore",
            "trash",
            "doctor",
        ):
            self.assertIn(cmd, r.stdout)

    def test_version(self):
        r = CliRunner().invoke(app, ["--version"])
        self.assertEqual(r.exit_code, 0)
        self.assertIn(__version__, r.stdout)  # whatever semantic-release set


class TestMainBoundary(unittest.TestCase):
    def test_keyboard_interrupt_exits_130(self):
        with (
            mock.patch("pystou.main.app", side_effect=KeyboardInterrupt),
            self.assertRaises(SystemExit) as cm,
        ):
            main()
        self.assertEqual(cm.exception.code, 130)

    def test_pystou_error_exits_1(self):
        with (
            mock.patch("pystou.main.app", side_effect=PystouError("boom")),
            self.assertRaises(SystemExit) as cm,
        ):
            main()
        self.assertEqual(cm.exception.code, 1)

    def test_unexpected_exception_exits_1(self):
        with (
            mock.patch("pystou.main.app", side_effect=RuntimeError("kaboom")),
            self.assertRaises(SystemExit) as cm,
        ):
            main()
        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
