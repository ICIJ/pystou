# PyStou

Welcome to **PyStou** – your ultimate toolkit for keeping your filesystem tidy and organized! Whether you're a developer drowning in duplicate folders or someone who loves archiving files but hates the clutter, PyStou is here to rescue you from chaos with style and efficiency.

**PyStou** is proudly developed by the [International Consortium of Investigative Journalists (ICIJ)](https://www.icij.org/), aiming to empower users with tools to manage and maintain large amounts of files.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Install from PyPI](#install-from-pypi)
  - [Install from source](#install-from-source)
- [Usage](#usage)
  - [Deduplicate Folders](#deduplicate-folders)
  - [Extract Archives](#extract-archives)
  - [Cleanup Junk Files](#cleanup-junk-files)
  - [Identify File Types](#identify-file-types)
  - [Directory Statistics](#directory-statistics)
  - [Empty Directories](#empty-directories)
  - [Restore & Trash](#restore--trash)
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
- Reversible deletes by default: cleanup, dedup, and extract quarantine removed items to `.pystou-trash/` — restore them any time with `pystou restore`, or reclaim space with `pystou trash purge`.
- Choose to interact with each file/archive or set default actions for seamless automation.
- Keep track of all actions with detailed JSON-formatted logs for easy troubleshooting.
- Pure native Python scripts ready to run out-of-the-box (except for necessary command-line tools).

## Installation

PyStou is published on [PyPI](https://pypi.org/project/pystou/) and installs in a single command.

### Prerequisites

- **Python 3.9 or higher** is required.
- **Command-Line Tools** (only needed for the matching archive formats):
  - **`p7zip-full`**: Required for extracting split ZIP archives (`.z01`, `.z02`, etc.).
  - **`pst-utils`**: Required for extracting `.pst` files.
  - **`zstd`**: Required for handling `.zst` files.

### Install from PyPI

Pick whichever tool you prefer.

With [**pip**](https://pip.pypa.io/):

```bash
pip install pystou
```

With [**pipx**](https://pipx.pypa.io/) (installs the CLI into its own isolated environment — recommended):

```bash
pipx install pystou
```

With [**uv**](https://docs.astral.sh/uv/):

```bash
uv tool install pystou
```

Once installed, the `pystou` command is available on your `PATH`:

```bash
pystou --help
```

### Install from source

For development, clone the repository and sync the environment with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/ICIJ/pystou.git
cd pystou
make install
```

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
- `--hard-delete`: Permanently delete instead of quarantining (skips `.pystou-trash/`).
- `--trash-dir PATH`: Use a custom trash directory instead of the default `.pystou-trash/` co-located with the target.
- `--log-dir LOG_DIR`: Directory to store log files (default: current directory).
- `--db-dir DB_DIR`: Directory to store index database (default: current directory).

> **Note:** Delete and merge actions quarantine removed items to `.pystou-trash/` by default.
> Use `pystou restore` to undo, or `pystou trash purge` to reclaim space.
> Pass `--hard-delete` to permanently delete immediately (old behavior).

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
  - `1`: Delete the archive after extraction (quarantined by default, see below).
  - `2`: Keep the archive after extraction.
- `-p N`, `--parallel N`: Number of parallel extraction workers (default: 1). Requires `-c` flag.
- `-N`, `--nested`: Recursively extract archives found inside extracted content.
- `--max-depth N`: Maximum nesting depth for `--nested` (default: 10).
- `-n`, `--dry-run`: Perform a dry run without making any changes.
- `--hard-delete`: Permanently delete source archives instead of quarantining them.
- `--trash-dir PATH`: Use a custom trash directory instead of the default `.pystou-trash/` co-located with the target.
- `--log-dir LOG_DIR`: Directory to store log files (default: current directory).
- `--db-dir DB_DIR`: Directory to store index database (default: current directory).

> **Note:** Source archives deleted after extraction are quarantined to `.pystou-trash/` by default.
> Use `pystou restore` to recover them, or `pystou trash purge` to reclaim space.
> Pass `--hard-delete` to permanently delete immediately (old behavior).

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
- `--hard-delete`: Permanently delete junk files instead of quarantining them.
- `--trash-dir PATH`: Use a custom trash directory instead of the default `.pystou-trash/` co-located with the target.

> **Note:** Junk files are quarantined to `.pystou-trash/` by default rather than permanently deleted.
> Use `pystou restore` to recover them, or `pystou trash purge` to reclaim space.
> Pass `--hard-delete` to permanently delete immediately (old behavior).

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

### Restore & Trash

**Purpose:** Manage the quarantine store — recover accidentally removed items or permanently reclaim
disk space. All destructive commands (`cleanup`, `dedup`, `extract`) quarantine items to a
`.pystou-trash/` directory by default instead of deleting them. These commands let you act on that
quarantine.

---

#### Restore Quarantined Items

**Command:**

```bash
pystou restore [directory] [options]
```

**Parameters:**

- `directory`: (Optional) Root directory whose `.pystou-trash/` to inspect. Defaults to the current directory.

**Options:**

- `--run ID`: Restore all items from a specific quarantine run (use `pystou trash list` to find IDs).
- `--all`: Restore every quarantined item across all runs.
- `--path ORIGINAL`: Restore a single item by its original absolute path.
- `--trash-dir PATH`: Use a custom trash directory instead of the default `.pystou-trash/` co-located with the target.
- `-n`, `--dry-run`: Show what would be restored without moving anything.

> Restore never overwrites an occupied path. If the original destination already exists, the item is
> left in the trash and reported as skipped.

**Examples:**

- **Restore a specific run:**

  ```bash
  pystou restore /path/to/folder --run 20260613_142501
  ```

- **Restore everything:**

  ```bash
  pystou restore /path/to/folder --all
  ```

- **Restore a single file by original path:**

  ```bash
  pystou restore /path/to/folder --path /path/to/folder/old-file.zip
  ```

---

#### List Quarantine Runs

**Purpose:** Display all quarantine runs with item counts and reclaimable disk space.

**Command:**

```bash
pystou trash list [directory] [options]
```

**Parameters:**

- `directory`: (Optional) Root directory whose `.pystou-trash/` to inspect. Defaults to the current directory.

**Options:**

- `--json`: Output run metadata in JSON format.

**Examples:**

- **List all runs (human-readable):**

  ```bash
  pystou trash list /path/to/folder
  ```

- **List runs as JSON:**

  ```bash
  pystou trash list /path/to/folder --json
  ```

---

#### Purge Quarantined Runs

**Purpose:** Permanently delete quarantined items — this is the *only* pystou command that truly
deletes data. Use it to reclaim disk space once you are confident the quarantined items are no
longer needed.

**Command:**

```bash
pystou trash purge [directory] [options]
```

**Parameters:**

- `directory`: (Optional) Root directory whose `.pystou-trash/` to purge. Defaults to the current directory.

**Options:**

- `--run ID`: Permanently delete a specific quarantine run.
- `--all`: Permanently delete all quarantine runs.
- `--older-than DAYS`: Permanently delete runs older than the given number of days.
- `--trash-dir PATH`: Use a custom trash directory instead of the default `.pystou-trash/` co-located with the target.
- `-n`, `--dry-run`: Show what would be deleted without removing anything.

**Examples:**

- **Purge a specific run:**

  ```bash
  pystou trash purge /path/to/folder --run 20260613_142501
  ```

- **Purge all runs:**

  ```bash
  pystou trash purge /path/to/folder --all
  ```

- **Purge runs older than 30 days:**

  ```bash
  pystou trash purge /path/to/folder --older-than 30
  ```

---

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
