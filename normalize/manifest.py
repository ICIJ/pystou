"""JSONL rename manifest: the record an Elasticsearch update replays.

Both paths are stored in full and in two forms. The base64 fields are the
lossless ones consumers key on; the plain fields are a printable rendering.
A path that failed to decode as UTF-8 cannot be written as a JSON string:
a lone surrogate is invalid per RFC 8259, so ``json.dumps`` emits a line that
Python reads back but ``jq`` and Elasticsearch can reject.
"""

import base64
import json
import os
from pathlib import Path
from typing import Optional, TextIO

from common import paths


def manifest_path(run_id: str, manifest_dir: Optional[str] = None) -> Path:
    """Returns the manifest file for a run.

    Args:
        run_id: Run identifier from :func:`common.trash.new_run_id`.
        manifest_dir: Optional override for the XDG state location.

    Returns:
        Path: ``<manifest dir>/<run_id>.jsonl``.
    """
    directory = Path(manifest_dir) if manifest_dir else paths.rename_dir()
    return directory / f"{run_id}.jsonl"


def printable(path: str) -> str:
    """Renders a path readably, escaping bytes that are not valid UTF-8.

    The result is for humans and is deliberately not round-trippable; use the
    matching ``*_b64`` field to recover the exact bytes.
    """
    return os.fsencode(path).decode("utf-8", "backslashreplace")


def encode(path: str) -> str:
    """Returns the exact bytes of a path, base64-encoded for safe JSON storage."""
    return base64.b64encode(os.fsencode(path)).decode("ascii")


def decode(value: str) -> str:
    """Turns a manifest ``*_b64`` field back into the exact original path str."""
    return os.fsdecode(base64.b64decode(value))


class ManifestWriter:
    """Appends manifest lines, fsyncing each one.

    Each line is durable on its own so a crash mid-run still leaves a manifest
    describing every rename but possibly the last: the rename lands on disk
    before its line is written, so a kill in that window loses one record.
    """

    def __init__(self, path: Path, meta: dict):
        self._path = path
        self._meta = meta
        self._file: Optional[TextIO] = None

    def __enter__(self) -> "ManifestWriter":
        return self

    def __exit__(self, *exc_info) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def record(self, kind: str, old: str, new: str, mode: str, rules: list[str]) -> None:
        """Appends one rename.

        Args:
            kind: ``file`` or ``dir``.
            old: Full path before the rename.
            new: Full path after the rename.
            mode: ``clean``, ``repaired``, or ``stripped``.
            rules: Rules that changed the name.
        """
        self._ensure_open()
        self._write(
            {
                "kind": kind,
                "old_b64": encode(old),
                "new_b64": encode(new),
                "old": printable(old),
                "new": printable(new),
                "mode": mode,
                "rules": rules,
            }
        )

    def _ensure_open(self) -> None:
        """Opens the manifest and writes its meta line, once, on the first record.

        Deferred so a run that renames nothing leaves no orphan file behind: an
        empty manifest is still a run id that ``--undo`` accepts.
        """
        if self._file is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # ManifestWriter is itself the context manager; __exit__ closes this.
        self._file = open(self._path, "a", encoding="utf-8")  # noqa: SIM115
        self._write({"meta": self._meta})

    def _write(self, obj: dict) -> None:
        assert self._file is not None, "ManifestWriter used outside its context manager"
        self._file.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())


def read(path: Path) -> tuple[dict, list[dict]]:
    """Reads a manifest.

    Args:
        path: Manifest file.

    Returns:
        tuple[dict, list[dict]]: The meta object and the rename entries, in
        file order, which is the order a consumer must replay them in.
    """
    meta: dict = {}
    entries: list[dict] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if "meta" in obj:
                meta = obj["meta"]
            else:
                entries.append(obj)
    return meta, entries
