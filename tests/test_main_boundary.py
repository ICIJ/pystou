# tests/test_main_boundary.py
import unittest
from unittest.mock import patch

import pystou.main as cli
from common.errors import InvalidDirectoryError


class TestTopLevelBoundary(unittest.TestCase):
    def _args(self, func):
        return type("Args", (), {"command": "extract", "func": staticmethod(func)})

    @patch("builtins.print")
    def test_pystou_error_exits_1(self, mock_print):
        def boom(_args):
            raise InvalidDirectoryError("bad dir")

        with patch.object(cli, "create_parser") as mk:
            mk.return_value.parse_args.return_value = self._args(boom)
            with self.assertRaises(SystemExit) as cm:
                cli.main()
        self.assertEqual(cm.exception.code, 1)

    @patch("builtins.print")
    def test_unexpected_error_exits_1(self, mock_print):
        def boom(_args):
            raise ValueError("kaboom")

        with patch.object(cli, "create_parser") as mk:
            mk.return_value.parse_args.return_value = self._args(boom)
            with self.assertRaises(SystemExit) as cm:
                cli.main()
        self.assertEqual(cm.exception.code, 1)

    @patch("builtins.print")
    def test_keyboard_interrupt_exits_130(self, mock_print):
        def boom(_args):
            raise KeyboardInterrupt

        with patch.object(cli, "create_parser") as mk:
            mk.return_value.parse_args.return_value = self._args(boom)
            with self.assertRaises(SystemExit) as cm:
                cli.main()
        self.assertEqual(cm.exception.code, 130)


if __name__ == "__main__":
    unittest.main()
