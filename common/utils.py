import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional, Union

from common.errors import PystouError
from common.fs_walker import walk
from common.safe_extract import safe_extract_tar, safe_extract_zip
from common.safe_ops import make_unique_dir, reserve_unique_file

EXTERNAL_TOOL_TIMEOUT_SECONDS = 3600

ARCHIVE_EXTENSIONS = frozenset(
    {
        ".zip",
        ".tar",
        ".tar.gz",
        ".tgz",
        ".tar.bz2",
        ".tbz",
        ".gz",
        ".bz2",
        ".tar.zst",
        ".tzst",
        ".zst",
        ".pst",
        ".ost",
    }
)


def group_directories(conn, root) -> dict:
    """Groups duplicate sibling directories based on their base names and parent directories.

    Args:
        conn: SQLite database connection.
        root: Directory the operation runs on; indexed paths outside it are ignored.

    Returns:
        dict: A dictionary where keys are group keys and values are lists of directory paths.
    """
    cursor = conn.cursor()
    pattern = re.compile(r"^(.*?)(?: \((\d+)\))?$")
    cursor.execute("SELECT path, parent_path FROM directories")
    root_prefix = os.path.abspath(root) + os.sep
    groups = defaultdict(list)
    # Iterate over cursor directly instead of fetchall() to reduce memory usage
    for row in cursor:
        path_str, parent_path_str = row
        if not os.path.abspath(path_str).startswith(root_prefix):
            continue
        dir_path = Path(path_str)
        parent_dir = Path(parent_path_str)
        dir_name = dir_path.name
        match = pattern.match(dir_name)
        if match:
            base_name = match.group(1)
            group_key = (str(parent_dir), base_name)
            groups[group_key].append(dir_path)
    # A suffixed name is only a copy of something when the plain name exists next to it:
    # 'Trip (2019)' and 'Trip (2020)' are distinct folders, not 'Trip' duplicated.
    return {
        (parent, base): dirs
        for (parent, base), dirs in groups.items()
        if len(dirs) > 1 and any(d.name == base for d in dirs)
    }


def get_archive_files(
    directory: Union[str, Path],
    recursive: bool,
    filter_types: Optional[list[str]] = None,
    threads: Optional[int] = None,
) -> list[Path]:
    """Returns a list of archive files in the directory.

    Args:
        directory (str or Path): The directory to search for archive files.
        recursive (bool): Whether to search recursively.
        filter_types (List[str], optional): List of archive types to include
            (e.g., ["pst", "zip", "tar.gz"]). If None, all types are included.
        threads (int, optional): Scan workers; None picks the default.

    Returns:
        List[Path]: A list of Paths to archive files.

    Raises:
        PystouError: If ``filter_types`` names an unsupported archive type.
    """
    if filter_types:
        # Normalize filter types to have leading dot
        normalized = frozenset(
            t.lower() if t.startswith(".") else f".{t.lower()}" for t in filter_types
        )
        unknown = normalized - ARCHIVE_EXTENSIONS
        if unknown:
            raise PystouError(
                f"Unknown archive type: {', '.join(sorted(unknown))}. "
                f"Accepted types: {', '.join(sorted(ARCHIVE_EXTENSIONS))}."
            )
        archive_extensions = normalized
    else:
        archive_extensions = ARCHIVE_EXTENSIONS
    # Pattern to match split archive parts (.z01, .z02, etc.)
    split_part_pattern = re.compile(r"\.z\d+$", re.IGNORECASE)

    archive_files: list[Path] = []
    directory_path = Path(directory)

    def is_archive(filename: str) -> bool:
        # Skip split archive parts - they'll be processed with their .zip
        if split_part_pattern.search(filename):
            return False
        return any(filename.lower().endswith(ext) for ext in archive_extensions)

    if recursive:
        for scan in walk(directory_path, threads=threads):
            if scan.error is not None:
                logging.warning(
                    {"action": "scan_error", "path": str(scan.path), "error": str(scan.error)}
                )
                continue
            for entry in scan.entries:
                # is_dir() follows symlinks, so a symlinked archive is still found,
                # exactly as os.walk listed it before.
                if not entry.is_dir() and is_archive(entry.name):
                    archive_files.append(scan.path / entry.name)
        archive_files.sort()
    else:
        for file in os.listdir(directory_path):
            file_path = directory_path / file
            if file_path.is_file() and is_archive(file):
                archive_files.append(file_path)
    return archive_files


def extract_archive(archive_path: Path, tolerant: bool = False) -> bool:
    """Extracts an archive file to its directory.

    A failure in one archive never aborts the caller's run: any exception raised by
    a format handler is reported and turned into a False return.

    Args:
        archive_path (Path): The path to the archive file.
        tolerant (bool): For Outlook (``.pst``/``.ost``) archives, keep partial
            output when readpst exits non-zero but wrote files. Ignored by other
            archive formats. Defaults to False.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    try:
        suffixes = "".join(archive_path.suffixes).lower()
        if suffixes.endswith(".zip"):
            # Check if this is a split archive
            split_parts = get_split_archive_parts(archive_path)
            if split_parts:
                return extract_split_zip_archive(archive_path)
            return extract_zip_archive(archive_path)
        elif (
            suffixes.endswith(".tar.gz")
            or suffixes.endswith(".tgz")
            or suffixes.endswith(".tar.bz2")
            or suffixes.endswith(".tbz")
            or suffixes.endswith(".tar")
        ):
            return extract_tar_archive(archive_path)
        elif suffixes.endswith(".gz") or suffixes.endswith(".bz2"):
            return extract_compressed_file(archive_path)
        elif (
            suffixes.endswith(".tar.zst") or suffixes.endswith(".tzst") or suffixes.endswith(".zst")
        ):
            return extract_zst_archive(archive_path)
        elif suffixes.endswith(".pst") or suffixes.endswith(".ost"):
            return extract_outlook_archive(archive_path, tolerant=tolerant)
        else:
            print(f"Unsupported archive format: {archive_path}", file=sys.stderr)
            logging.error(
                {
                    "action": "extract",
                    "status": "unsupported_format",
                    "archive": str(archive_path),
                }
            )
            return False
    except Exception as e:
        print(f"Error extracting archive {archive_path}: {e}", file=sys.stderr)
        logging.error(
            {
                "action": "extract",
                "status": "error",
                "archive": str(archive_path),
                "error": str(e),
            }
        )
        return False


def extract_zip_archive(archive_path: Path) -> bool:
    """Extracts a ZIP archive into a unique directory named after the archive.

    Args:
        archive_path (Path): The path to the ZIP archive.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    output_dir = make_unique_dir(archive_path.parent / archive_path.stem)
    try:
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            if not safe_extract_zip(zip_ref, output_dir):
                print(
                    f"Refused unsafe ZIP archive (path traversal): {archive_path}",
                    file=sys.stderr,
                )
                shutil.rmtree(output_dir, ignore_errors=True)
                return False
        print(f"Extracted ZIP archive to {output_dir}", file=sys.stderr)
        return True
    except Exception as e:
        shutil.rmtree(output_dir, ignore_errors=True)
        print(f"Error extracting ZIP archive {archive_path}: {e}", file=sys.stderr)
        logging.error(
            {
                "action": "extract_zip",
                "status": "error",
                "archive": str(archive_path),
                "error": str(e),
            }
        )
        return False


def extract_split_zip_archive(archive_path: Path) -> bool:
    """Extracts a split ZIP archive into a unique directory using the 7z command.

    Args:
        archive_path (Path): The path to the main .zip file of the split archive.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    if shutil.which("7z") is None:
        print(
            "7z command not found. Please install p7zip-full to extract split ZIP archives.",
            file=sys.stderr,
        )
        logging.error(
            {
                "action": "extract_split_zip",
                "status": "missing_dependency",
                "archive": str(archive_path),
            }
        )
        return False

    output_dir = make_unique_dir(archive_path.parent / archive_path.stem)
    cmd = ["7z", "x", f"-o{output_dir}", "-y", "--", str(archive_path)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=EXTERNAL_TOOL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        shutil.rmtree(output_dir, ignore_errors=True)
        print(f"Error extracting split ZIP archive {archive_path}: {e}", file=sys.stderr)
        logging.error(
            {
                "action": "extract_split_zip",
                "status": "error",
                "archive": str(archive_path),
                "error": str(e),
            }
        )
        return False

    # 7-Zip exits 1 for non-fatal warnings (e.g. a skipped file); 2 and above are fatal.
    if proc.returncode > 1:
        diagnostics = ((proc.stderr or "").strip() or (proc.stdout or "").strip())[-2000:]
        shutil.rmtree(output_dir, ignore_errors=True)
        print(
            f"Error extracting split ZIP archive {archive_path}: "
            f"7z exited with status {proc.returncode}",
            file=sys.stderr,
        )
        if diagnostics:
            print(diagnostics, file=sys.stderr)
        logging.error(
            {
                "action": "extract_split_zip",
                "status": "error",
                "returncode": proc.returncode,
                "archive": str(archive_path),
                "sevenzip_output": diagnostics,
            }
        )
        return False

    print(f"Extracted split ZIP archive to {output_dir}", file=sys.stderr)
    return True


def _tar_output_dir(archive_path: Path) -> Path:
    """Creates and returns the unique directory a tar-based archive extracts into.

    Args:
        archive_path (Path): The archive being extracted.

    Returns:
        Path: The freshly created output directory, named after the archive with any
        intermediate ``.tar`` dropped (``backup.tar.gz`` -> ``backup``).
    """
    base_name = re.sub(r"\.tar$", "", archive_path.stem, flags=re.IGNORECASE)
    return make_unique_dir(archive_path.parent / base_name)


def extract_tar_archive(archive_path: Path) -> bool:
    """Extracts a TAR archive into a unique directory named after the archive.

    Args:
        archive_path (Path): The path to the TAR archive.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    output_dir = _tar_output_dir(archive_path)
    try:
        with tarfile.open(archive_path, "r:*") as tar_ref:
            if not safe_extract_tar(tar_ref, output_dir):
                print(
                    f"Refused unsafe TAR archive (unsafe member): {archive_path}",
                    file=sys.stderr,
                )
                shutil.rmtree(output_dir, ignore_errors=True)
                return False
        print(f"Extracted TAR archive to {output_dir}", file=sys.stderr)
        return True
    except Exception as e:
        shutil.rmtree(output_dir, ignore_errors=True)
        print(f"Error extracting TAR archive {archive_path}: {e}", file=sys.stderr)
        logging.error(
            {
                "action": "extract_tar",
                "status": "error",
                "archive": str(archive_path),
                "error": str(e),
            }
        )
        return False


def extract_compressed_file(archive_path: Path) -> bool:
    """Extracts a compressed file (.gz, .bz2) to a non-clobbering target.

    Args:
        archive_path (Path): The path to the compressed file.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    target_path = None
    try:
        if archive_path.suffix.lower() == ".gz":
            import gzip

            target_path = reserve_unique_file(archive_path.with_suffix(""))
            with (
                gzip.open(archive_path, "rb") as f_in,
                open(target_path, "wb") as f_out,
            ):
                shutil.copyfileobj(f_in, f_out)
        elif archive_path.suffix.lower() == ".bz2":
            import bz2

            target_path = reserve_unique_file(archive_path.with_suffix(""))
            with bz2.open(archive_path, "rb") as f_in, open(target_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            print(f"Unsupported compressed file format: {archive_path}", file=sys.stderr)
            logging.error(
                {
                    "action": "extract_compressed_file",
                    "status": "unsupported_format",
                    "archive": str(archive_path),
                }
            )
            return False
        print(f"Extracted compressed file: {archive_path}", file=sys.stderr)
        return True
    except Exception as e:
        if target_path is not None and target_path.exists():
            target_path.unlink()
        print(f"Error extracting compressed file {archive_path}: {e}", file=sys.stderr)
        logging.error(
            {
                "action": "extract_compressed_file",
                "status": "error",
                "archive": str(archive_path),
                "error": str(e),
            }
        )
        return False


def extract_zst_archive(archive_path: Path) -> bool:
    """Extracts a Zstandard compressed file or TAR.ZST archive.

    Args:
        archive_path (Path): The path to the ZST or TAR.ZST archive.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    try:
        import zstandard as zstd

        return _extract_zst_with_module(archive_path, zstd)
    except ImportError:
        pass  # Module not installed, try using the zstd command-line tool

    if shutil.which("zstd") is not None:
        return _extract_zst_with_command(archive_path)
    else:
        print(
            "Zstandard module and zstd command-line tool not found. Please install one of them to extract .zst files.",
            file=sys.stderr,
        )
        logging.error(
            {
                "action": "extract_zst",
                "status": "missing_dependency",
                "archive": str(archive_path),
            }
        )
        return False


def _extract_zst_with_module(archive_path: Path, zstd: Any) -> bool:
    """Extracts a ZST archive using the zstandard module.

    Args:
        archive_path (Path): The path to the ZST archive.
        zstd (module): The imported zstandard module.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    suffixes = "".join(archive_path.suffixes).lower()
    is_tar = ".tar.zst" in suffixes or ".tzst" in suffixes
    if is_tar:
        temp_tar_path = reserve_unique_file(archive_path.with_suffix(".tar"))
        output_dir = _tar_output_dir(archive_path)
        try:
            with open(archive_path, "rb") as f_in, open(temp_tar_path, "wb") as f_out:
                zstd.ZstdDecompressor().copy_stream(f_in, f_out)
            with tarfile.open(temp_tar_path, "r") as tar_ref:
                if not safe_extract_tar(tar_ref, output_dir):
                    print(f"Refused unsafe TAR.ZST archive: {archive_path}", file=sys.stderr)
                    shutil.rmtree(output_dir, ignore_errors=True)
                    return False
            print(f"Extracted TAR.ZST archive to {output_dir}", file=sys.stderr)
            return True
        except Exception as e:
            shutil.rmtree(output_dir, ignore_errors=True)
            print(f"Error extracting ZST archive {archive_path}: {e}", file=sys.stderr)
            logging.error(
                {
                    "action": "extract_zst_module",
                    "status": "error",
                    "archive": str(archive_path),
                    "error": str(e),
                }
            )
            return False
        finally:
            if temp_tar_path.exists():
                temp_tar_path.unlink()
    else:
        target_path = None
        try:
            target_path = reserve_unique_file(archive_path.with_suffix(""))
            with open(archive_path, "rb") as f_in, open(target_path, "wb") as f_out:
                zstd.ZstdDecompressor().copy_stream(f_in, f_out)
            print(f"Decompressed ZST file: {archive_path}", file=sys.stderr)
            return True
        except Exception as e:
            if target_path is not None and target_path.exists():
                target_path.unlink()
            print(f"Error extracting ZST archive {archive_path}: {e}", file=sys.stderr)
            logging.error(
                {
                    "action": "extract_zst_module",
                    "status": "error",
                    "archive": str(archive_path),
                    "error": str(e),
                }
            )
            return False


def _extract_zst_with_command(archive_path: Path) -> bool:
    """Extracts a ZST archive using the zstd command-line tool.

    Args:
        archive_path (Path): The path to the ZST archive.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    suffixes = "".join(archive_path.suffixes).lower()
    is_tar = ".tar.zst" in suffixes or ".tzst" in suffixes
    # Claim the output directory before reserving the temp file, so the durable
    # artifact gets the clean name and only the throwaway is suffixed.
    output_dir = _tar_output_dir(archive_path) if is_tar else None
    output_path = reserve_unique_file(archive_path.with_suffix(""))
    keep_output = False
    try:
        cmd = ["zstd", "-d", "-f", "-o", str(output_path), "--", str(archive_path)]
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=EXTERNAL_TOOL_TIMEOUT_SECONDS,
        )
        if output_dir is not None:
            with tarfile.open(output_path, "r") as tar_ref:
                if not safe_extract_tar(tar_ref, output_dir):
                    print(f"Refused unsafe TAR.ZST archive: {archive_path}", file=sys.stderr)
                    shutil.rmtree(output_dir, ignore_errors=True)
                    return False
            print(f"Extracted TAR.ZST archive to {output_dir}", file=sys.stderr)
            return True
        keep_output = True  # the decompressed plain file IS the result
        print(f"Decompressed ZST file using zstd command: {archive_path}", file=sys.stderr)
        return True
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        tarfile.TarError,
        OSError,
    ) as e:
        if output_dir is not None:
            shutil.rmtree(output_dir, ignore_errors=True)
        print(
            f"Error extracting ZST archive with zstd command {archive_path}: {e}", file=sys.stderr
        )
        logging.error(
            {
                "action": "extract_zst_command",
                "status": "error",
                "archive": str(archive_path),
                "error": str(e),
            }
        )
        return False
    finally:
        # Remove the reserved output unless it is the kept plain-file result.
        # For a TAR.ZST the decompressed .tar is always a temp to discard; on any
        # failure or abrupt exit (e.g. KeyboardInterrupt) the placeholder is removed.
        if not keep_output and output_path.exists():
            output_path.unlink()


def _collapse_redundant_root(output_dir: Path) -> None:
    """Collapse a single redundant nested root directory.

    If ``output_dir`` holds exactly one entry and it is a directory, lift that
    directory's contents up into ``output_dir`` and remove the now-empty
    wrapper. ``readpst`` in recursive mode (``-r``) writes its tree inside a folder named after the PST,
    one level below the unique directory pystou created — yielding
    ``output_dir/<root>/<mail folders>``. This collapses that single redundant
    level. It is a no-op when ``output_dir`` is empty, holds more than one
    entry, or holds a single non-directory entry.

    Args:
        output_dir (Path): The unique directory pystou created for the PST.
    """
    entries = list(output_dir.iterdir())
    if len(entries) != 1 or not entries[0].is_dir() or entries[0].is_symlink():
        return
    inner_name = entries[0].name
    wrapper_tmp = make_unique_dir(output_dir.parent / f"{output_dir.name}.tmp")
    output_dir.rename(wrapper_tmp)
    try:
        (wrapper_tmp / inner_name).rename(output_dir)
    except OSError:
        # The inner rename failed and output_dir is still vacated; restore the
        # original directory so output_dir is never left missing, then re-raise.
        wrapper_tmp.rename(output_dir)
        raise
    wrapper_tmp.rmdir()


def _has_extracted_files(output_dir: Path) -> bool:
    """Returns True if ``output_dir`` exists and holds at least one regular file."""
    return output_dir.is_dir() and any(p.is_file() for p in output_dir.rglob("*"))


def _safe_collapse(output_dir: Path, action: str, archive_path: Path) -> None:
    """Collapses the redundant readpst root, logging (but not raising) on failure."""
    try:
        _collapse_redundant_root(output_dir)
    except OSError as e:
        logging.warning(
            {
                "action": action,
                "status": "collapse_failed",
                "archive": str(archive_path),
                "error": str(e),
            }
        )


def extract_outlook_archive(archive_path: Path, tolerant: bool = False) -> bool:
    """Extracts an Outlook PST or OST file using readpst into a unique folder.

    PST and OST share the same on-disk format, so readpst handles both with the
    same flags. The structured log ``action`` stays distinct per format
    (``extract_pst`` / ``extract_ost``) so logs can be filtered by type.

    ``readpst`` (libpst) is known to exit non-zero on some files — notably modern
    Office 365 ``.ost`` caches — while still writing a substantially complete mail
    tree. By default a non-zero exit is treated as a failure: the partial output is
    removed and the source archive is left untouched. When ``tolerant`` is True, a
    non-zero exit that nonetheless produced files is kept and reported as success
    (with a ``partial_extraction`` warning). readpst's own diagnostics and exit code
    are always captured and logged on a non-zero exit.

    Args:
        archive_path (Path): The path to the PST or OST file.
        tolerant (bool): Keep partial output when readpst exits non-zero but wrote
            files, instead of discarding it. Defaults to False (strict).

    Returns:
        bool: True if extraction was successful (or partial under ``tolerant``),
        False otherwise.
    """
    is_ost = archive_path.suffix.lower() == ".ost"
    action = "extract_ost" if is_ost else "extract_pst"
    label = "OST" if is_ost else "PST"

    if shutil.which("readpst") is None:
        print(
            "readpst command not found. Please install readpst to extract .pst and .ost files.",
            file=sys.stderr,
        )
        logging.error(
            {
                "action": action,
                "status": "missing_dependency",
                "archive": str(archive_path),
            }
        )
        return False

    base_output_dir = archive_path.parent / archive_path.stem
    unique_output_dir = make_unique_dir(base_output_dir)
    cmd = ["readpst", "-reD", "-o", str(unique_output_dir), "--", str(archive_path)]
    try:
        # errors="replace": readpst echoes mail folder names (often non-ASCII) to its
        # output; never let a stray byte raise UnicodeDecodeError mid-extraction.
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=EXTERNAL_TOOL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"Error extracting {label} file {archive_path}: {e}", file=sys.stderr)
        logging.error(
            {
                "action": action,
                "status": "error",
                "archive": str(archive_path),
                "error": str(e),
            }
        )
        shutil.rmtree(unique_output_dir, ignore_errors=True)
        return False

    if proc.returncode != 0:
        # readpst prints diagnostics to stderr; fall back to stdout. Cap the tail
        # kept in the log so a chatty run can't bloat the log record.
        diagnostics = (proc.stderr or "").strip() or (proc.stdout or "").strip()
        diag_tail = diagnostics[-2000:]
        if tolerant and _has_extracted_files(unique_output_dir):
            print(
                f"{label} extraction completed with errors (readpst exit "
                f"{proc.returncode}); keeping partial output: {archive_path}",
                file=sys.stderr,
            )
            logging.warning(
                {
                    "action": action,
                    "status": "partial_extraction",
                    "returncode": proc.returncode,
                    "archive": str(archive_path),
                    "output_dir": str(unique_output_dir),
                    "readpst_output": diag_tail,
                }
            )
            _safe_collapse(unique_output_dir, action, archive_path)
            return True

        print(
            f"Error extracting {label} file {archive_path}: "
            f"readpst exited with status {proc.returncode}",
            file=sys.stderr,
        )
        if diag_tail:
            print(diag_tail, file=sys.stderr)
        logging.error(
            {
                "action": action,
                "status": "error",
                "returncode": proc.returncode,
                "archive": str(archive_path),
                "readpst_output": diag_tail,
            }
        )
        shutil.rmtree(unique_output_dir, ignore_errors=True)
        return False

    _safe_collapse(unique_output_dir, action, archive_path)
    if not _has_extracted_files(unique_output_dir):
        print(f"{label} extraction produced no output: {archive_path}", file=sys.stderr)
        logging.warning(
            {
                "action": action,
                "status": "no_output",
                "archive": str(archive_path),
            }
        )
        return False
    print(f"Extracted {label} file to {unique_output_dir}", file=sys.stderr)
    return True


def get_split_archive_parts(archive_path: Path) -> list[Path]:
    """Finds all parts of a split ZIP archive.

    Given a .zip file, finds all related split parts (.z01, .z02, etc.).
    Returns sorted list of all parts (including the .zip), or empty list if not a split archive.

    Args:
        archive_path (Path): The path to the .zip file.

    Returns:
        List[Path]: Sorted list of all split archive parts, or empty list if not split.
    """
    if archive_path.suffix.lower() != ".zip":
        return []

    base_name = archive_path.stem
    parent_dir = archive_path.parent

    # Find all .zXX parts
    parts = []
    pattern = re.compile(rf"^{re.escape(base_name)}\.z(\d+)$", re.IGNORECASE)

    for file in parent_dir.iterdir():
        if file.is_file():
            match = pattern.match(file.name)
            if match:
                parts.append((int(match.group(1)), file))

    if not parts:
        return []  # Not a split archive

    # Sort by part number and return just the paths
    parts.sort(key=lambda x: x[0])
    return [p[1] for p in parts] + [archive_path]
