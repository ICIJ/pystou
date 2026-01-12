"""Cursor utilities for terminal progress display."""

import atexit
import signal
import sys
from typing import Optional

# ANSI escape codes for cursor control
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

# Track cursor state
_cursor_hidden = False
_original_sigint: Optional[signal.Handlers] = None
_original_sigterm: Optional[signal.Handlers] = None


def hide_cursor() -> None:
    """Hides the terminal cursor and registers cleanup handlers."""
    global _cursor_hidden, _original_sigint, _original_sigterm

    if _cursor_hidden:
        return

    # Only hide if stdout is a terminal
    if not sys.stdout.isatty():
        return

    sys.stdout.write(HIDE_CURSOR)
    sys.stdout.flush()
    _cursor_hidden = True

    # Register atexit handler for normal exit
    atexit.register(show_cursor)

    # Store original signal handlers and install our own
    _original_sigint = signal.getsignal(signal.SIGINT)
    _original_sigterm = signal.getsignal(signal.SIGTERM)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


def show_cursor() -> None:
    """Shows the terminal cursor and removes cleanup handlers."""
    global _cursor_hidden, _original_sigint, _original_sigterm

    if not _cursor_hidden:
        return

    # Only show if stdout is a terminal
    if sys.stdout.isatty():
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()

    _cursor_hidden = False

    # Unregister atexit handler
    try:
        atexit.unregister(show_cursor)
    except Exception:
        pass

    # Restore original signal handlers
    if _original_sigint is not None:
        try:
            signal.signal(signal.SIGINT, _original_sigint)
        except Exception:
            pass
        _original_sigint = None

    if _original_sigterm is not None:
        try:
            signal.signal(signal.SIGTERM, _original_sigterm)
        except Exception:
            pass
        _original_sigterm = None


def _signal_handler(signum: int, frame) -> None:
    """Signal handler that restores cursor before re-raising."""
    global _original_sigint, _original_sigterm

    # Capture original handlers BEFORE show_cursor clears them
    if signum == signal.SIGINT and _original_sigint is not None:
        original = _original_sigint
    elif signum == signal.SIGTERM and _original_sigterm is not None:
        original = _original_sigterm
    else:
        original = signal.SIG_DFL

    # Restore cursor (this clears _original_sigint/_original_sigterm)
    show_cursor()

    # Re-raise with original handler
    if original == signal.SIG_DFL:
        # Default behavior - raise KeyboardInterrupt for SIGINT
        if signum == signal.SIGINT:
            raise KeyboardInterrupt
        else:
            sys.exit(128 + signum)
    elif original != signal.SIG_IGN and callable(original):
        original(signum, frame)
