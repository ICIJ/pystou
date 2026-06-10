import unittest
from unittest.mock import patch

import common.interrupt as interrupt
from common.interrupt import scanning


class TestScanning(unittest.TestCase):
    @patch.object(interrupt, "show_cursor")
    @patch.object(interrupt, "hide_cursor")
    def test_normal_exit_shows_cursor(self, mock_hide, mock_show):
        with scanning("scan"):
            pass
        mock_hide.assert_called_once()
        self.assertTrue(mock_show.called)

    @patch("builtins.print")
    @patch.object(interrupt, "show_cursor")
    @patch.object(interrupt, "hide_cursor")
    def test_keyboard_interrupt_exits_130(self, mock_hide, mock_show, mock_print):
        with self.assertRaises(SystemExit) as cm:
            with scanning("scan"):
                raise KeyboardInterrupt
        self.assertEqual(cm.exception.code, 130)
        self.assertTrue(mock_show.called)  # cursor restored


if __name__ == "__main__":
    unittest.main()
