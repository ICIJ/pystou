"""Typed exceptions used to distinguish expected failures from bugs."""


class PystouError(Exception):
    """Base class for expected, explained PyStou errors."""


class InvalidDirectoryError(PystouError):
    """Raised when a target directory is missing or is not a directory."""
