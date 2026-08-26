#!/usr/bin/env python3
"""Normalize subcommand: make filenames valid, portable UTF-8 for S3."""

import contextlib
import logging
import os
import shlex
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.table import Table

from common import console
from common.cli import (
    DirectoryArg,
    DryRunOpt,
    LogDirOpt,
    ManifestDirOpt,
    RecursiveOpt,
    ThreadsOpt,
)
from common.errors import PystouError
from common.fs_walker import is_excluded_dir, walk
from common.logger import setup_logging
from common.safe_ops import make_unique_dir, reserve_unique_file
from common.trash import RUN_ID_RE, new_run_id
from common.validation import validate_directory_or_exit
from normalize import manifest
from normalize.rules import RULES, normalize_name
from pystou import __version__

STAGING_SUFFIX = ".pystou-staging"


class Rule(str, Enum):
    utf8 = "utf8"
    nfc = "nfc"
    control = "control"
    punct = "punct"
    astral = "astral"
    all = "all"


def normalize_command(
    directory: DirectoryArg = ".",
    recursive: RecursiveOpt = False,
    threads: ThreadsOpt = None,
    undo: Annotated[
        Optional[str], typer.Option("--undo", help="Undo a previous run by its run id.")
    ] = None,
    rule: Annotated[
        Optional[list[Rule]],
        typer.Option("--rule", help="utf8|nfc|control|punct|astral|all (repeatable)."),
    ] = None,
    dry_run: DryRunOpt = False,
    summary: Annotated[
        bool,
        typer.Option("-s", "--summary", help="Print counts instead of one row per path."),
    ] = False,
    no_manifest: Annotated[
        bool,
        typer.Option("--no-manifest", help="Skip the rename manifest; the run cannot be undone."),
    ] = False,
    manifest_dir: ManifestDirOpt = None,
    log_dir: LogDirOpt = None,
) -> None:
    """Rename files whose names are not valid, portable UTF-8 (S3-safe)."""
    setup_logging("normalize", log_dir)
    selected = _selected_rules(rule)
    logging.info(
        {
            "action": "configuration",
            "command": "normalize",
            "directory": directory,
            "recursive": recursive,
            "threads": threads,
            "rules": list(selected),
            "dry_run": dry_run,
            "summary": summary,
            "no_manifest": no_manifest,
            "undo": undo,
        }
    )
    if no_manifest and manifest_dir:
        raise PystouError("--no-manifest and --manifest-dir contradict each other.")
    if undo:
        restored, skipped = undo_run(undo, manifest_dir, dry_run, summary)
        verb = "Would restore" if dry_run else "Restored"
        if summary:
            console.print_table(_summary_table("Undo", verb, restored, "Skipped", skipped))
        console.success(f"{verb} {restored} name(s)" + (f", skipped {skipped}" if skipped else ""))
        return
    # Absolute, because the manifest is replayed against Elasticsearch and an
    # undo runs from an arbitrary cwd. abspath, not resolve(): resolving a
    # symlinked ancestor would report paths the consumer never indexed.
    root = Path(os.path.abspath(validate_directory_or_exit(directory)))

    run_id = new_run_id()
    path = manifest.manifest_path(run_id, manifest_dir)
    # printable(): a root or argv carrying invalid bytes would otherwise make
    # json.dumps raise UnicodeEncodeError and abort the run before any rename.
    meta = {
        "run": run_id,
        "root": manifest.printable(str(root)),
        "root_b64": manifest.encode(str(root)),
        "argv": manifest.printable(shlex.join(sys.argv)),
        "version": __version__,
        "rules": list(selected),
    }

    records = not dry_run and not no_manifest
    writing = manifest.ManifestWriter(path, meta) if records else contextlib.nullcontext()

    renamed, failed, table = _run(root, recursive, selected, dry_run, summary, writing, threads)

    if not renamed and not failed:
        console.status("No filenames need normalizing.")
        return
    if summary:
        verb = "Would rename" if dry_run else "Renamed"
        table = _summary_table("Normalize", verb, renamed, "Failed", failed)
    console.print_table(table)
    if dry_run:
        console.status(
            f"Dry run: would rename {renamed} item(s). "
            "Collision suffixes are resolved at rename time and may differ."
        )
        return
    console.success(f"Renamed {renamed} item(s)" + (f", {failed} failed" if failed else ""))
    if not renamed:
        return
    if records:
        console.status(f"Manifest: {path}")
        return
    console.warn("No manifest was written: this run cannot be undone.")


def _summary_table(title: str, verb: str, count: int, failed_label: str, failed: int) -> Table:
    """Builds the two-metric table ``-s`` prints in place of one row per path."""
    table = console.table(title, ["Metric", "Count"])
    table.add_row(verb, f"{count:,}")
    if failed:
        table.add_row(failed_label, f"{failed:,}")
    return table


def _selected_rules(rule: Optional[list[Rule]]) -> tuple[str, ...]:
    """Expands the repeatable --rule option, defaulting to every rule."""
    if not rule or Rule.all in rule:
        return RULES
    return tuple(r.value for r in rule)


def _run(
    root: Path,
    recursive: bool,
    rules: tuple[str, ...],
    dry_run: bool,
    summary: bool,
    writing,
    threads: Optional[int] = None,
) -> tuple[int, int, Table]:
    """Walks, renames, and records into ``writing``. Returns (renamed, failed, table).

    ``writing`` is the caller's manifest context: a ``ManifestWriter`` when the
    run records, or a null context when it does not.

    Under ``summary`` the table is left empty rather than filled and discarded:
    a tree with a million renames would otherwise hold a million rows the
    caller never prints.
    """
    table = console.table("Renames", ["Old", "New", "Mode"])
    renamed = 0
    failed = 0
    with writing as writer:
        for old, kind in walk_bottom_up(root, recursive, threads):
            new_name, mode, applied = normalize_name(old.name, rules)
            if new_name == old.name:
                continue
            if dry_run:
                if not summary:
                    table.add_row(
                        manifest.printable(str(old)),
                        manifest.printable(str(old.parent / new_name)),
                        mode,
                    )
                renamed += 1
                continue
            try:
                new = apply_rename(old, new_name)
            except OSError as e:
                failed += 1
                console.error(f"Cannot rename {manifest.printable(str(old))}: {e}")
                logging.error(
                    {
                        "action": "rename",
                        "status": "error",
                        "path": manifest.printable(str(old)),
                        "error": str(e),
                    }
                )
                continue
            if writer is not None:
                writer.record(kind, str(old), str(new), mode, applied)
            if not summary:
                table.add_row(manifest.printable(str(old)), manifest.printable(str(new)), mode)
            renamed += 1
            logging.info(
                {
                    "action": "rename",
                    "status": "success",
                    "kind": kind,
                    "mode": mode,
                    "old": manifest.printable(str(old)),
                    "new": manifest.printable(str(new)),
                }
            )
    return renamed, failed, table


def walk_bottom_up(
    root: Path, recursive: bool, threads: Optional[int] = None
) -> list[tuple[Path, str]]:
    """Lists everything under ``root``, deepest first, excluding ``root`` itself.

    Children must be renamed while their parent still carries its old name, so
    the manifest replays correctly. Sorting by descending depth gives that; the
    path breaks ties so two runs over the same tree agree.

    Args:
        root: Directory to walk. Never included in the result.
        recursive: Whether to descend past the top level.
        threads: Scan workers; None picks the default.

    Returns:
        list[tuple[Path, str]]: ``(path, kind)`` pairs, kind being ``file`` or
        ``dir``, ordered so every child precedes its parent.
    """
    entries: list[tuple[Path, str]] = []
    for scan in walk(root, recursive=recursive, threads=threads):
        if scan.error is not None:
            logging.warning(
                {"action": "scan_error", "path": str(scan.path), "error": str(scan.error)}
            )
            continue
        for entry in scan.entries:
            if is_excluded_dir(entry.name):
                continue
            # A symlink to a directory is renamed as a leaf, never descended into.
            kind = "dir" if entry.is_dir(follow_symlinks=False) else "file"
            entries.append((scan.path / entry.name, kind))
    entries.sort(key=lambda item: (-len(item[0].parts), str(item[0])))
    return entries


def apply_rename(old: Path, new_name: str) -> Path:
    """Renames ``old`` to ``new_name`` in place without ever clobbering.

    Bare ``os.rename`` silently replaces an existing file on POSIX, so the
    target is claimed first: an exclusively created empty file, or an
    exclusively created empty directory (which ``rename`` is allowed to
    replace). Symlinks are renamed, never followed.

    Args:
        old: Existing path.
        new_name: Desired basename.

    Returns:
        Path: The path the entry now lives at, which carries a ``' (n)'``
        suffix if the desired name was taken.
    """
    target = old.parent / new_name
    is_directory = old.is_dir() and not old.is_symlink()
    # os.rename is a no-op when both paths resolve to one file, so a target that
    # already IS the source (a case- or normalization-insensitive volume) or
    # merely shares its inode (a hardlink) must be moved aside before renaming.
    # Skipping that would report and record a rename that never happened.
    if _is_same_entry(old, target):
        return _rename_through_staging(old, target, is_directory)
    claimed = _claim(target, is_directory)
    _rename_onto_claim(old, claimed)
    return claimed


def _is_same_entry(old: Path, target: Path) -> bool:
    """Returns True when ``target`` exists and resolves to the same file as ``old``."""
    if not os.path.lexists(target):
        return False
    return os.path.samestat(os.lstat(old), os.lstat(target))


def _claim(target: Path, is_directory: bool) -> Path:
    """Exclusively creates a placeholder at ``target``, or at ``target (n)`` if taken."""
    if is_directory:
        return make_unique_dir(target)
    return reserve_unique_file(target, keep_suffix=True)


def _rename_onto_claim(old: Path, claimed: Path) -> None:
    """Renames ``old`` onto its placeholder, releasing the placeholder on failure.

    The placeholder carries the name the caller asked for, so leaving it behind
    would push the real entry to ``name (1)`` on the next run.
    """
    try:
        os.rename(old, claimed)
    except OSError:
        _release(claimed)
        raise


def _release(claimed: Path) -> None:
    """Removes a placeholder we created but could not rename onto."""
    with contextlib.suppress(OSError):
        if claimed.is_dir():
            claimed.rmdir()
        else:
            claimed.unlink()


def _rename_through_staging(old: Path, target: Path, is_directory: bool) -> Path:
    """Renames an entry that shares its directory entry or inode with ``target``.

    Moving ``old`` aside first makes the two paths distinguishable: if ``target``
    is gone afterwards it was the same directory entry, so the name is free; if
    it survives it was a separate link and the usual collision suffix applies.
    """
    staged = _claim(old.with_name(f"{old.name}{STAGING_SUFFIX}"), is_directory)
    _rename_onto_claim(old, staged)
    try:
        if not os.path.lexists(target):
            os.rename(staged, target)
            return target
        claimed = _claim(target, is_directory)
        _rename_onto_claim(staged, claimed)
        return claimed
    except OSError:
        os.rename(staged, old)
        raise


def undo_run(
    run_id: str,
    manifest_dir: Optional[str] = None,
    dry_run: bool = False,
    summary: bool = False,
) -> tuple[int, int]:
    """Renames everything in a manifest back to its original name.

    Entries are replayed in reverse (directories before the files they
    contain), which is the order that keeps every recorded path valid.

    An occupied target is skipped rather than suffixed: an undo that invents a
    name is not an undo.

    Args:
        run_id: Run identifier of the manifest to replay.
        manifest_dir: Optional override for the XDG state location.
        dry_run: Report what would be restored or skipped without renaming
            anything.
        summary: Count skipped entries instead of naming each one.

    Returns:
        tuple[int, int]: ``(restored, skipped)`` counts. In a dry run,
        ``restored`` counts entries that would be restored.
    """
    if not RUN_ID_RE.fullmatch(run_id):
        raise PystouError(f"Not a run id: {run_id}. Expected a value like 20260819T101500Z-3f2a.")
    path = manifest.manifest_path(run_id, manifest_dir)
    try:
        _meta, entries = manifest.read(path)
    except FileNotFoundError as e:
        raise PystouError(f"No manifest for run {run_id} in {path.parent}.") from e
    restored = 0
    skipped = 0
    # entries are deepest-first (child-before-parent), which is also the order
    # these substitutions must apply in: a descendant's recorded ``new`` path
    # is expressed using its ancestor's *old* name.
    moves = [(manifest.decode(e["old_b64"]), manifest.decode(e["new_b64"])) for e in entries]
    for entry in reversed(entries):
        new_path = manifest.decode(entry["new_b64"])
        source = Path(_resolve_current_path(new_path, moves) if dry_run else new_path)
        target = Path(manifest.decode(entry["old_b64"]))
        if not os.path.lexists(source):
            skipped += 1
            if not summary:
                console.warn(f"Missing, cannot undo: {entry['new']}")
            continue
        if os.path.lexists(target):
            skipped += 1
            if not summary:
                console.warn(f"Occupied, cannot undo: {entry['old']}")
            continue
        if dry_run:
            restored += 1
            continue
        try:
            # Deliberately not the forward path's claim-then-rename: an undo
            # that invents a ' (n)' name is not an undo, so the check above is
            # a plain lexists and the window between it and the rename is
            # accepted.
            os.rename(source, target)
        except OSError as e:
            skipped += 1
            console.error(f"Cannot undo {entry['new']}: {e}")
            logging.error(
                {"action": "undo", "status": "error", "path": entry["new"], "error": str(e)}
            )
            continue
        restored += 1
        logging.info(
            {"action": "undo", "status": "success", "old": entry["new"], "new": entry["old"]}
        )
    return restored, skipped


def _resolve_current_path(path: str, moves: list[tuple[str, str]]) -> str:
    """Rewrites a recorded ``new`` path to where it actually sits on disk.

    A descendant's recorded path is expressed using its ancestor's *old*
    name, since the ancestor had not been renamed yet when the descendant
    was. With two or more renamed levels above it, a descendant's path needs
    every one of those ancestors' substitutions applied, not just the first
    that matches. A real undo self-corrects: renaming each ancestor back
    physically moves the descendant along with it. A dry run changes nothing
    on disk, so this substitutes every ancestor's actual current (``new``)
    name in turn instead.

    Args:
        path: A recorded ``new`` path, decoded.
        moves: ``(old, new)`` pairs for every entry in the manifest, deepest
            first: the order their substitutions must be applied in, since a
            child's own prefix has to give way before its parent's does.

    Returns:
        str: The path as it actually exists on disk right now.
    """
    for old_prefix, new_prefix in moves:
        if path == old_prefix:
            path = new_prefix
        else:
            prefixed = old_prefix + os.sep
            if path.startswith(prefixed):
                path = new_prefix + os.sep + path[len(prefixed) :]
    return path
