"""Typed exceptions used to distinguish expected failures from bugs."""


class PystouError(Exception):
    """Base class for expected, explained PyStou errors."""


class InvalidDirectoryError(PystouError):
    """Raised when a target directory is missing or is not a directory."""


class CrossDeviceTrashError(PystouError):
    """Raised when a target is on a different filesystem than the trash root."""


class TrashUnavailableError(PystouError):
    """Raised when the trash directory cannot be created (e.g. read-only root)."""


class UndecodablePathError(PystouError):
    """Raised when a path cannot be stored in the index because it is not valid UTF-8."""

    def __init__(self, path: str):
        self.path = path
        printable = path.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")
        super().__init__(
            f"Cannot index {printable}: the name is not valid UTF-8. "
            f"Run 'pystou normalize' on this tree first."
        )
