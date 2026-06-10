"""Context manager that manages the cursor and converts Ctrl-C into exit 130."""

import logging
import sys
from contextlib import contextmanager

from common.cursor import hide_cursor, show_cursor


@contextmanager
def scanning(action_label: str = "scan"):
    """Hides the cursor for the duration; on KeyboardInterrupt, exits cleanly (130).

    Args:
        action_label (str): Label used in the interruption message and log
            (e.g. "scan", "removal").
    """
    hide_cursor()
    try:
        yield
    except KeyboardInterrupt:
        print(f"\n{action_label.capitalize()} interrupted by user.")
        logging.info({"action": f"{action_label}_interrupted"})
        sys.exit(130)
    finally:
        show_cursor()
