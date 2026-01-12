# PyStou

Welcome to **PyStou** – your ultimate toolkit for keeping your filesystem tidy and organized! Whether you're a developer drowning in duplicate folders or someone who loves archiving files but hates the clutter, PyStou is here to rescue you from chaos with style and efficiency.

**PyStou** is proudly developed by the [International Consortium of Investigative Journalists (ICIJ)](https://www.icij.org/), aiming to empower users with tools to manage and maintain large amounts of files.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Clone the Repository](#clone-the-repository)
  - [Install the Package](#install-the-package)
- [Usage](#usage)
  - [Deduplicate Folders](#deduplicate-folders)
  - [Extract Archives](#extract-archives)
  - [Cleanup Junk Files](#cleanup-junk-files)
  - [Identify File Types](#identify-file-types)
  - [Directory Statistics](#directory-statistics)
  - [Empty Directories](#empty-directories)
- [Running Tests](#running-tests)
- [License](#license)

## Features

- Automatically identify and manage duplicate directories, ensuring you only keep what you need.
- Effortlessly extract a wide range of archive formats, including `.zip`, `.tar.gz`, `.zst`, and `.pst`.
- Support for split ZIP archives (`.z01`, `.z02`, etc.) with automatic detection.
- Nested archive extraction for archives containing other archives.
- Parallel archive extraction for faster processing of multiple archives.
- Remove junk files (`.DS_Store`, `Thumbs.db`, `__MACOSX`, etc.) with a single command.
- Detect file type mismatches and encrypted archives.
- Get comprehensive directory statistics including file counts, sizes, and types.
- Find and remove empty directories safely.
- Choose to interact with each file/archive or set default actions for seamless automation.
- Keep track of all actions with detailed JSON-formatted logs for easy troubleshooting.
- Pure native Python scripts ready to run out-of-the-box (except for necessary command-line tools).

## Installation

Getting started with PyStou is a breeze! Follow the steps below to install and set up the project on your machine.

### Prerequisites

- **Python 3.7 or higher** is required.
- **Command-Line Tools:**
  - **`p7zip-full`**: Required for extracting split ZIP archives (`.z01`, `.z02`, etc.).
  - **`pst-utils`**: Required for extracting `.pst` files.
  - **`zstd`**: Required for handling `.zst` files.

### Clone the Repository

```bash
git clone https://github.com/ICIJ/pystou.git
cd pystou
```

### Install the Package

PyStou can be installed using `pip`. It includes all necessary components without additional dependencies.

```bash
pip install .
```

> **Note:** You might need to use `pip3` and/or `sudo` depending on your system configuration.

## Usage

PyStou provides a unified command-line interface with several subcommands.

```bash
pystou --help
pystou dedup --help
pystou extract --help
pystou cleanup --help
pystou identify --help
pystou stats --help
pystou empty --help
```

### Deduplicate Folders

**Purpose:** Identify and manage duplicate directories to keep your filesystem clean.

**Command:**

```bash
pystou dedup [directory] [options]
```

**Parameters:**

- `directory`: (Optional) The root directory to start scanning from. Defaults to the current directory if not specified.

**Options:**

- `-r`, `--recursive`: Recursively process subdirectories.
- `-l LEVEL`, `--level LEVEL`: Maximum depth level for recursion (default: unlimited).
- `-c CHOICE`, `--default-choice CHOICE`: Default action to apply to all duplicate groups.
  - `1`: Delete duplicates.
  - `2`: Merge contents and delete duplicates.
  - `3`: Skip (do nothing).
- `-n`, `--dry-run`: Perform a dry run without making any changes.
- `--log-dir LOG_DIR`: Directory to store log files (default: current directory).
- `--db-dir DB_DIR`: Directory to store index database (default: current directory).

**Examples:**

- **Interactive Mode:**

  ```bash
  pystou dedup /path/to/your/folders -r
  ```

  *The script will prompt you for each duplicate group found.*

- **Automated Mode with Default Choice (Delete Duplicates):**

  ```bash
  pystou dedup /path/to/your/folders -r -c 1
  ```

- **Dry Run Mode:**

  ```bash
  pystou dedup /path/to/your/folders -r -n
  ```

### Extract Archives

**Purpose:** Extract various archive formats efficiently and manage them post-extraction.

**Supported Formats:**
- Standard: `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz`, `.gz`, `.bz2`
- Zstandard: `.zst`, `.tar.zst`, `.tzst`
- Outlook: `.pst`
- Split ZIP: `.z01`, `.z02`, ... (automatically detected with main `.zip` file)

**Command:**

```bash
pystou extract [directory] [options]
```

**Parameters:**

- `directory`: (Optional) The root directory to start searching for archives. Defaults to the current directory if not specified.

**Options:**

- `-r`, `--recursive`: Recursively search subdirectories for archives.
- `-c CHOICE`, `--default-choice CHOICE`: Default action to apply to all archives.
  - `1`: Extract archives.
  - `2`: Skip (do nothing).
- `-dc DELETE_CHOICE`, `--default-delete-choice DELETE_CHOICE`: Default action when prompted to delete archives after extraction.
  - `1`: Delete the archive after extraction.
  - `2`: Keep the archive after extraction.
- `-p N`, `--parallel N`: Number of parallel extraction workers (default: 1). Requires `-c` flag.
- `-N`, `--nested`: Recursively extract archives found inside extracted content.
- `--max-depth N`: Maximum nesting depth for `--nested` (default: 10).
- `-n`, `--dry-run`: Perform a dry run without making any changes.
- `--log-dir LOG_DIR`: Directory to store log files (default: current directory).
- `--db-dir DB_DIR`: Directory to store index database (default: current directory).

**Examples:**

- **Interactive Mode:**

  ```bash
  pystou extract /path/to/archives -r
  ```

  *The script will prompt you for each archive found, asking whether to extract or skip.*

- **Automated Mode with Default Choices (Extract and Delete Archives):**

  ```bash
  pystou extract /path/to/archives -r -c 1 -dc 1
  ```

- **Parallel Extraction (4 workers):**

  ```bash
  pystou extract /path/to/archives -r -c 1 -dc 2 -p 4
  ```

- **Nested Extraction (archives inside archives):**

  ```bash
  pystou extract /path/to/archives -r -c 1 -dc 1 --nested
  ```

- **Dry Run Mode:**

  ```bash
  pystou extract /path/to/archives -r -n
  ```

### Cleanup Junk Files

**Purpose:** Remove common junk files created by operating systems and applications.

**Removed by default:**
- macOS: `.DS_Store`, `._.DS_Store`, `._*` files, `__MACOSX`, `.AppleDouble`, `.Spotlight-V100`, `.Trashes`, `.fseventsd`, `.TemporaryItems`, `.LSOverride`
- Windows: `Thumbs.db`, `ehthumbs.db`, `ehthumbs_vista.db`, `desktop.ini`

**Command:**

```bash
pystou cleanup [directory] [options]
```

**Options:**

- `-r`, `--recursive`: Recursively process subdirectories.
- `--include PATTERN`: Additional file/directory names to remove (can be used multiple times).
- `--list-only`: Only list junk files without removing them.
- `-n`, `--dry-run`: Perform a dry run without making any changes.

**Examples:**

- **List junk files:**

  ```bash
  pystou cleanup /path/to/folder -r --list-only
  ```

- **Remove junk files:**

  ```bash
  pystou cleanup /path/to/folder -r
  ```

- **Remove additional patterns:**

  ```bash
  pystou cleanup /path/to/folder -r --include ".gitkeep" --include "*.bak"
  ```

### Identify File Types

**Purpose:** Detect file types and find potential issues like mismatched extensions or encrypted archives.

**Command:**

```bash
pystou identify [directory] [options]
```

**Options:**

- `-r`, `--recursive`: Recursively process subdirectories.
- `--check-mismatch`: Check for files with mismatched extensions.
- `--check-encrypted`: Check for encrypted ZIP archives.
- `--check-all`: Run all checks.
- `--extensions EXT`: Comma-separated list of extensions to check (e.g., `.zip,.pdf`).

**Examples:**

- **Find mismatched extensions:**

  ```bash
  pystou identify /path/to/folder -r --check-mismatch
  ```

- **Find encrypted archives:**

  ```bash
  pystou identify /path/to/folder -r --check-encrypted
  ```

- **Run all checks on specific extensions:**

  ```bash
  pystou identify /path/to/folder -r --check-all --extensions ".zip,.pdf,.docx"
  ```

### Directory Statistics

**Purpose:** Display comprehensive statistics about files and directories.

**Command:**

```bash
pystou stats [directory] [options]
```

**Options:**

- `-r`, `--recursive`: Recursively process subdirectories.
- `--top N`: Number of top items to show (default: 10).
- `--by-extension`: Show breakdown by file extension.
- `--by-size`: Show largest files.
- `--json`: Output statistics in JSON format.

**Examples:**

- **Show directory statistics:**

  ```bash
  pystou stats /path/to/folder -r
  ```

- **Show largest files:**

  ```bash
  pystou stats /path/to/folder -r --by-size --top 20
  ```

- **Output as JSON:**

  ```bash
  pystou stats /path/to/folder -r --json
  ```

### Empty Directories

**Purpose:** Find and remove empty directories.

**Command:**

```bash
pystou empty [directory] [options]
```

**Options:**

- `-r`, `--recursive`: Recursively process subdirectories.
- `--list-only`: Only list empty directories without removing them.
- `--include-hidden`: Include hidden directories (starting with `.`).
- `-n`, `--dry-run`: Perform a dry run without making any changes.

**Examples:**

- **List empty directories:**

  ```bash
  pystou empty /path/to/folder -r --list-only
  ```

- **Remove empty directories:**

  ```bash
  pystou empty /path/to/folder -r
  ```

- **Include hidden directories:**

  ```bash
  pystou empty /path/to/folder -r --include-hidden
  ```

## Running Tests

PyStou includes a suite of unit tests to ensure everything works smoothly. Here's how to run them:

```bash
make test
```

Or manually:

```bash
python3 -m unittest discover tests
```

> **Note:** Ensure you have all necessary command-line tools installed (`readpst`, `zstd`, `7z`) before running tests that involve archive extraction.

## License

Distributed under the [MIT License](LICENSE). See `LICENSE` for more information.
