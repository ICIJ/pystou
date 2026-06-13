"""Typed exceptions used to distinguish expected failures from bugs."""


class PystouError(Exception):
    """Base class for expected, explained PyStou errors."""


class InvalidDirectoryError(PystouError):
    """Raised when a target directory is missing or is not a directory."""


class CrossDeviceTrashError(PystouError):
    """Raised when a target is on a different filesystem than the trash root."""


class TrashUnavailableError(PystouError):
    """Raised when the trash directory cannot be created (e.g. read-only root)."""
