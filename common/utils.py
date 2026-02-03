import os
import re
import shutil
import subprocess
import tarfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, List, Optional, Union

import logging


def group_directories(conn) -> dict:
    """Groups duplicate sibling directories based on their base names and parent directories.

    Args:
        conn: SQLite database connection.

    Returns:
        dict: A dictionary where keys are group keys and values are lists of directory paths.
    """
    cursor = conn.cursor()
    pattern = re.compile(r"^(.*?)(?: \((\d+)\))?$")
    cursor.execute("SELECT path, parent_path FROM directories")
    groups = defaultdict(list)
    # Iterate over cursor directly instead of fetchall() to reduce memory usage
    for row in cursor:
        path_str, parent_path_str = row
        dir_path = Path(path_str)
        parent_dir = Path(parent_path_str)
        dir_name = dir_path.name
        match = pattern.match(dir_name)
        if match:
            base_name = match.group(1)
            group_key = (str(parent_dir), base_name)
            groups[group_key].append(dir_path)
    # Only keep groups with more than one directory
    duplicate_groups = {k: v for k, v in groups.items() if len(v) > 1}
    return duplicate_groups


def get_directory_size(conn, dir_path: Path) -> tuple:
    """Calculates the total size and number of files in a directory using the database.

    Args:
        conn: SQLite database connection.
        dir_path (Path): Path to the directory.

    Returns:
        tuple: Total size in bytes and number of files.
    """
    cursor = conn.cursor()
    # Use SQL aggregate functions instead of fetching all rows
    cursor.execute(
        "SELECT COALESCE(SUM(size), 0), COUNT(*) FROM files WHERE directory_path = ?",
        (str(dir_path),)
    )
    total_size, num_files = cursor.fetchone()
    return total_size, num_files


def summarize_group(group_key, dir_paths: List[Path], conn) -> None:
    """Prints a summary of a group of duplicate directories.

    Args:
        group_key: The group key (parent directory and base name).
        dir_paths (List[Path]): List of directory paths in the group.
        conn: SQLite database connection.
    """
    parent_dir, base_name = group_key
    print(f"\nFound duplicate directories in '{parent_dir}': '{base_name}'")
    for dir_path in sorted(dir_paths):
        size, num_files = get_directory_size(conn, dir_path)
        formatted_size = f"{size:,}"
        formatted_num_files = f"{num_files:,}"
        print(
            f" - {dir_path.name} : {formatted_num_files} files, {formatted_size} bytes"
        )


def get_archive_files(
    directory: Union[str, Path],
    recursive: bool,
    filter_types: Optional[List[str]] = None,
) -> List[Path]:
    """Returns a list of archive files in the directory.

    Args:
        directory (str or Path): The directory to search for archive files.
        recursive (bool): Whether to search recursively.
        filter_types (List[str], optional): List of archive types to include
            (e.g., ["pst", "zip", "tar.gz"]). If None, all types are included.

    Returns:
        List[Path]: A list of Paths to archive files.
    """
    all_extensions = [
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
    ]

    if filter_types:
        # Normalize filter types to have leading dot
        normalized = [t if t.startswith(".") else f".{t}" for t in filter_types]
        archive_extensions = [ext for ext in all_extensions if ext in normalized]
    else:
        archive_extensions = all_extensions
    # Pattern to match split archive parts (.z01, .z02, etc.)
    split_part_pattern = re.compile(r"\.z\d+$", re.IGNORECASE)

    archive_files: List[Path] = []
    directory_path = Path(directory)

    def is_archive(filename: str) -> bool:
        # Skip split archive parts - they'll be processed with their .zip
        if split_part_pattern.search(filename):
            return False
        return any(filename.endswith(ext) for ext in archive_extensions)

    if recursive:
        for root, _, files in os.walk(directory_path):
            for file in files:
                if is_archive(file):
                    archive_files.append(Path(root) / file)
    else:
        for file in os.listdir(directory_path):
            file_path = directory_path / file
            if file_path.is_file() and is_archive(file):
                archive_files.append(file_path)
    return archive_files


def extract_archive(archive_path: Path) -> bool:
    """Extracts an archive file to its directory.

    Args:
        archive_path (Path): The path to the archive file.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    try:
        suffixes = "".join(archive_path.suffixes)
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
            suffixes.endswith(".tar.zst")
            or suffixes.endswith(".tzst")
            or suffixes.endswith(".zst")
        ):
            return extract_zst_archive(archive_path)
        elif suffixes.endswith(".pst"):
            return extract_pst_archive(archive_path)
        else:
            print(f"Unsupported archive format: {archive_path}")
            logging.error(
                {
                    "action": "extract",
                    "status": "unsupported_format",
                    "archive": str(archive_path),
                }
            )
            return False
    except Exception as e:
        print(f"Error extracting archive {archive_path}: {e}")
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
    """Extracts a ZIP archive.

    Args:
        archive_path (Path): The path to the ZIP archive.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    try:
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(archive_path.parent)
        print(f"Extracted ZIP archive: {archive_path}")
        return True
    except Exception as e:
        print(f"Error extracting ZIP archive {archive_path}: {e}")
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
    """Extracts a split ZIP archive using 7z command.

    Args:
        archive_path (Path): The path to the main .zip file of the split archive.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    if shutil.which("7z") is None:
        print(
            "7z command not found. Please install p7zip-full to extract split ZIP archives."
        )
        logging.error(
            {
                "action": "extract_split_zip",
                "status": "missing_dependency",
                "archive": str(archive_path),
            }
        )
        return False

    try:
        output_dir = archive_path.parent
        cmd = ["7z", "x", str(archive_path), f"-o{output_dir}", "-y"]
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"Extracted split ZIP archive: {archive_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error extracting split ZIP archive {archive_path}: {e}")
        logging.error(
            {
                "action": "extract_split_zip",
                "status": "error",
                "archive": str(archive_path),
                "error": str(e),
            }
        )
        return False


def extract_tar_archive(archive_path: Path) -> bool:
    """Extracts a TAR archive.

    Args:
        archive_path (Path): The path to the TAR archive.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    try:
        with tarfile.open(archive_path, "r:*") as tar_ref:
            tar_ref.extractall(archive_path.parent)
        print(f"Extracted TAR archive: {archive_path}")
        return True
    except Exception as e:
        print(f"Error extracting TAR archive {archive_path}: {e}")
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
    """Extracts a compressed file (e.g., .gz, .bz2).

    Args:
        archive_path (Path): The path to the compressed file.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    try:
        if archive_path.suffix == ".gz":
            import gzip

            target_path = archive_path.with_suffix("")
            with gzip.open(archive_path, "rb") as f_in, open(
                target_path, "wb"
            ) as f_out:
                shutil.copyfileobj(f_in, f_out)
        elif archive_path.suffix == ".bz2":
            import bz2

            target_path = archive_path.with_suffix("")
            with bz2.open(archive_path, "rb") as f_in, open(target_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            print(f"Unsupported compressed file format: {archive_path}")
            logging.error(
                {
                    "action": "extract_compressed_file",
                    "status": "unsupported_format",
                    "archive": str(archive_path),
                }
            )
            return False
        print(f"Extracted compressed file: {archive_path}")
        return True
    except Exception as e:
        print(f"Error extracting compressed file {archive_path}: {e}")
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
            "Zstandard module and zstd command-line tool not found. Please install one of them to extract .zst files."
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
    try:
        if ".tar.zst" in "".join(archive_path.suffixes) or ".tzst" in "".join(
            archive_path.suffixes
        ):
            # Extract TAR.ZST archive
            temp_tar_path = archive_path.with_suffix(".tar")
            with open(archive_path, "rb") as f_in, open(temp_tar_path, "wb") as f_out:
                dctx = zstd.ZstdDecompressor()
                dctx.copy_stream(f_in, f_out)
            with tarfile.open(temp_tar_path, "r") as tar_ref:
                tar_ref.extractall(archive_path.parent)
            temp_tar_path.unlink()
            print(f"Extracted TAR.ZST archive: {archive_path}")
        else:
            # Decompress .zst file
            target_path = archive_path.with_suffix("")
            with open(archive_path, "rb") as f_in, open(target_path, "wb") as f_out:
                dctx = zstd.ZstdDecompressor()
                dctx.copy_stream(f_in, f_out)
            print(f"Decompressed ZST file: {archive_path}")
        return True
    except Exception as e:
        print(f"Error extracting ZST archive {archive_path}: {e}")
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
    try:
        cmd = ["zstd", "-d", str(archive_path), "-o", str(archive_path.with_suffix(""))]
        subprocess.run(cmd, check=True)
        if ".tar.zst" in "".join(archive_path.suffixes) or ".tzst" in "".join(
            archive_path.suffixes
        ):
            # Extract the resulting .tar file
            temp_tar_path = archive_path.with_suffix(".tar")
            with tarfile.open(temp_tar_path, "r") as tar_ref:
                tar_ref.extractall(archive_path.parent)
            temp_tar_path.unlink()
            print(f"Extracted TAR.ZST archive using zstd command: {archive_path}")
        else:
            print(f"Decompressed ZST file using zstd command: {archive_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error extracting ZST archive with zstd command {archive_path}: {e}")
        logging.error(
            {
                "action": "extract_zst_command",
                "status": "error",
                "archive": str(archive_path),
                "error": str(e),
            }
        )
        return False


def extract_pst_archive(archive_path: Path) -> bool:
    """Extracts a PST file using readpst, ensuring the output is in a unique folder.

    Args:
        archive_path (Path): The path to the PST file.

    Returns:
        bool: True if extraction was successful, False otherwise.
    """
    if shutil.which("readpst") is None:
        print(
            "readpst command not found. Please install readpst to extract .pst files."
        )
        logging.error(
            {
                "action": "extract_pst",
                "status": "missing_dependency",
                "archive": str(archive_path),
            }
        )
        return False

    try:
        base_output_dir = archive_path.parent / archive_path.stem
        unique_output_dir = get_unique_folder_name(base_output_dir)
        # Create the output directory if it does not exist
        os.makedirs(unique_output_dir, exist_ok=True)
        cmd = ["readpst", "-reD", "-o", str(unique_output_dir), str(archive_path)]
        subprocess.run(cmd, check=True)
        print(f"Extracted PST file to {unique_output_dir}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error extracting PST file {archive_path}: {e}")
        logging.error(
            {
                "action": "extract_pst",
                "status": "error",
                "archive": str(archive_path),
                "error": str(e),
            }
        )
        return False


def get_split_archive_parts(archive_path: Path) -> List[Path]:
    """Finds all parts of a split ZIP archive.

    Given a .zip file, finds all related split parts (.z01, .z02, etc.).
    Returns sorted list of all parts (including the .zip), or empty list if not a split archive.

    Args:
        archive_path (Path): The path to the .zip file.

    Returns:
        List[Path]: Sorted list of all split archive parts, or empty list if not split.
    """
    if not archive_path.suffix.lower() == ".zip":
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


def get_unique_folder_name(base_dir: Path) -> Path:
    """Generates a unique folder name by appending '(n)' suffix if necessary.

    Args:
        base_dir (Path): The initial desired directory path.

    Returns:
        Path: A unique directory path that does not already exist.
    """
    if not base_dir.exists():
        return base_dir

    counter = 1
    while True:
        new_dir = Path(f"{base_dir} ({counter})")
        if not new_dir.exists():
            return new_dir
        counter += 1
