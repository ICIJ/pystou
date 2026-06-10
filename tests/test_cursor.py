import unittest
import signal
from unittest.mock import patch, MagicMock

from common.cursor import (
    hide_cursor,
    show_cursor,
    _signal_handler,
    HIDE_CURSOR,
    SHOW_CURSOR,
)


class TestCursorHide(unittest.TestCase):
    """Tests for cursor hiding functionality."""

    def setUp(self):
        """Reset cursor state before each test."""
        import common.cursor

        common.cursor._cursor_hidden = False
        common.cursor._original_sigint = None
        common.cursor._original_sigterm = None

    def tearDown(self):
        """Ensure cursor is shown after each test."""
        show_cursor()

    @patch("sys.stdout.isatty", return_value=True)
    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    def test_hide_cursor_writes_escape_code(self, mock_flush, mock_write, mock_isatty):
        """Test that hide_cursor writes the correct escape code."""
        hide_cursor()
        mock_write.assert_called_with(HIDE_CURSOR)
        mock_flush.assert_called()

    @patch("sys.stdout.isatty", return_value=False)
    @patch("sys.stdout.write")
    def test_hide_cursor_skips_non_tty(self, mock_write, mock_isatty):
        """Test that hide_cursor does nothing if not a TTY."""
        hide_cursor()
        mock_write.assert_not_called()

    @patch("sys.stdout.isatty", return_value=True)
    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    def test_hide_cursor_idempotent(self, mock_flush, mock_write, mock_isatty):
        """Test that hide_cursor only hides once."""
        hide_cursor()
        hide_cursor()  # Second call should do nothing
        self.assertEqual(mock_write.call_count, 1)


class TestCursorShow(unittest.TestCase):
    """Tests for cursor showing functionality."""

    def setUp(self):
        """Reset cursor state before each test."""
        import common.cursor

        common.cursor._cursor_hidden = False
        common.cursor._original_sigint = None
        common.cursor._original_sigterm = None

    @patch("sys.stdout.isatty", return_value=True)
    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    def test_show_cursor_writes_escape_code(self, mock_flush, mock_write, mock_isatty):
        """Test that show_cursor writes the correct escape code."""
        import common.cursor

        common.cursor._cursor_hidden = True

        show_cursor()
        mock_write.assert_called_with(SHOW_CURSOR)
        mock_flush.assert_called()

    @patch("sys.stdout.isatty", return_value=True)
    @patch("sys.stdout.write")
    def test_show_cursor_does_nothing_if_not_hidden(self, mock_write, mock_isatty):
        """Test that show_cursor does nothing if cursor not hidden."""
        show_cursor()  # Cursor wasn't hidden
        mock_write.assert_not_called()


class TestCursorSignalHandler(unittest.TestCase):
    """Tests for signal handler functionality."""

    def setUp(self):
        """Reset cursor state before each test."""
        import common.cursor

        common.cursor._cursor_hidden = False
        common.cursor._original_sigint = None
        common.cursor._original_sigterm = None

    def tearDown(self):
        """Ensure cursor is shown after each test."""
        show_cursor()

    @patch("sys.stdout.isatty", return_value=True)
    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    def test_signal_handler_restores_cursor(self, mock_flush, mock_write, mock_isatty):
        """Test that signal handler restores cursor before raising."""
        import common.cursor

        common.cursor._cursor_hidden = True
        common.cursor._original_sigint = signal.SIG_DFL

        with self.assertRaises(KeyboardInterrupt):
            _signal_handler(signal.SIGINT, None)

        # Should have written show cursor escape code
        mock_write.assert_called_with(SHOW_CURSOR)

    @patch("sys.stdout.isatty", return_value=True)
    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    def test_signal_handler_calls_original(self, mock_flush, mock_write, mock_isatty):
        """Test that signal handler calls original handler."""
        import common.cursor

        common.cursor._cursor_hidden = True

        original_handler = MagicMock()
        common.cursor._original_sigint = original_handler

        _signal_handler(signal.SIGINT, None)

        original_handler.assert_called_once_with(signal.SIGINT, None)


class TestCursorIntegration(unittest.TestCase):
    """Integration tests for cursor functionality."""

    def setUp(self):
        """Reset cursor state before each test."""
        import common.cursor

        common.cursor._cursor_hidden = False
        common.cursor._original_sigint = None
        common.cursor._original_sigterm = None

    def tearDown(self):
        """Ensure cursor is shown after each test."""
        show_cursor()

    @patch("sys.stdout.isatty", return_value=True)
    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    def test_hide_show_cycle(self, mock_flush, mock_write, mock_isatty):
        """Test full hide/show cycle."""
        hide_cursor()
        self.assertEqual(mock_write.call_args_list[0][0][0], HIDE_CURSOR)

        show_cursor()
        self.assertEqual(mock_write.call_args_list[1][0][0], SHOW_CURSOR)

    @patch("sys.stdout.isatty", return_value=True)
    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    @patch("signal.getsignal")
    @patch("signal.signal")
    def test_signal_handlers_registered(
        self, mock_signal, mock_getsignal, mock_flush, mock_write, mock_isatty
    ):
        """Test that signal handlers are registered on hide_cursor."""
        mock_getsignal.return_value = signal.SIG_DFL

        hide_cursor()

        # Should register handlers for SIGINT and SIGTERM
        signal_calls = [call[0][0] for call in mock_signal.call_args_list]
        self.assertIn(signal.SIGINT, signal_calls)
        self.assertIn(signal.SIGTERM, signal_calls)


if __name__ == "__main__":
    unittest.main()
