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
  - [Global Options](#global-options)
  - [Deduplicate Folders](#deduplicate-folders)
  - [Extract Archives](#extract-archives)
  - [Cleanup Junk Files](#cleanup-junk-files)
  - [Identify File Types](#identify-file-types)
  - [Directory Statistics](#directory-statistics)
  - [Empty Directories](#empty-directories)
  - [Restore & Trash](#restore--trash)
  - [Doctor](#doctor)
- [Migrating from 0.x](#migrating-from-0x)
- [Running Tests](#running-tests)
- [License](#license)

## Features

- Automatically identify and manage duplicate directories, ensuring you only keep what you need.
- Effortlessly extract a wide range of archive formats, including `.zip`, `.tar.gz`, `.zst`, `.pst`, and `.ost`.
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
- Rich terminal output: tables, progress bars, colored status indicators, and interactive prompts.
- Global `--no-color` and `-q/--quiet` flags for scripting and CI pipelines.
- Shell completion for bash, zsh, and fish via `pystou --install-completion`.
- `pystou doctor` verifies that all required external tools are installed.

## Installation

PyStou is published on [PyPI](https://pypi.org/project/pystou/) and installs in a single command.

### Prerequisites

- **Python 3.9 or higher** is required.
- **Python dependencies**: `pip install pystou` automatically installs `typer` and `rich`. PyStou is no longer zero-dependency.
- **Command-Line Tools** (only needed for the matching archive formats):
  - **`p7zip-full`**: Required for extracting split ZIP archives (`.z01`, `.z02`, etc.).
  - **`pst-utils`**: Required for extracting Outlook `.pst` and `.ost` files (both use `readpst`).
  - **`zstd`**: Required for handling `.zst` files.

  Run `pystou doctor` after installation to verify all external tools are present.

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
pystou restore --help
pystou trash --help
pystou doctor --help
```

### Global Options

These options apply to every subcommand and must be placed before the subcommand name.

| Flag | Description |
|------|-------------|
| `--no-color` | Disable all colored output. Useful for piping or CI environments. |
| `-q`, `--quiet` | Suppress progress bars and status messages; only errors are shown. |
| `--version` | Print the installed version and exit. |
| `--install-completion` | Install shell completion for the current shell (bash, zsh, fish). |
| `--show-completion` | Print the completion script so you can copy or customize it. |

**Examples:**

```bash
# Run dedup with no color output
pystou --no-color dedup /path/to/folder -r

# Run extract quietly (suitable for cron jobs)
pystou --quiet extract /path/to/archives -r --action extract

# Install shell completion
pystou --install-completion
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
- `-l N`, `--level N`: Maximum recursion depth.
- `--action delete|merge|skip`: Default action to apply to all duplicate groups (omit to prompt per group).
- `-n`, `--dry-run`: Perform a dry run without making any changes.
- `--hard-delete`: Permanently delete instead of quarantining (skips `.pystou-trash/`).
- `--trash-dir PATH`: Use a custom trash directory instead of the default `.pystou-trash/` co-located with the target.
- `--log-dir PATH`: Directory to store log files (default: current directory).
- `--db-dir PATH`: Directory to store index database (default: current directory).

> **Note:** Delete and merge actions quarantine removed items to `.pystou-trash/` by default.
> Use `pystou restore` to undo, or `pystou trash purge` to reclaim space.
> Pass `--hard-delete` to permanently delete immediately (old behavior).

**Examples:**

- **Interactive Mode:**

  ```bash
  pystou dedup /path/to/your/folders -r
  ```

  *PyStou will prompt you for each duplicate group found.*

- **Automated Mode — Delete Duplicates:**

  ```bash
  pystou dedup /path/to/your/folders -r --action delete
  ```

- **Automated Mode — Merge Contents:**

  ```bash
  pystou dedup /path/to/your/folders -r --action merge
  ```

- **Dry Run Mode:**

  ```bash
  pystou dedup /path/to/your/folders -r -n
  ```

### Extract Archives

**Purpose:** Extract various archive formats efficiently and manage them post-extraction.

**Output layout:** each archive is extracted into its own directory next to it, named after the
archive (`photos.zip` -> `photos/`, `backup.tar.gz` -> `backup/`). If that name is taken, a numbered
one is used instead (`photos (1)/`), so extracting never overwrites existing files.

**Supported Formats:**
- Standard: `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz`, `.gz`, `.bz2`
- Zstandard: `.zst`, `.tar.zst`, `.tzst`
- Outlook: `.pst`, `.ost`
- Split ZIP: `.z01`, `.z02`, ... (automatically detected with main `.zip` file)

**Command:**

```bash
pystou extract [directory] [options]
```

**Parameters:**

- `directory`: (Optional) The root directory to start searching for archives. Defaults to the current directory if not specified.

**Options:**

- `-r`, `--recursive`: Recursively search subdirectories for archives.
- `--action extract|skip`: Default action to apply to all archives (omit to prompt per archive).
- `--remove-archives` / `--keep-archives`: Remove (quarantine) source archives after successful extraction, or keep them (default: `--keep-archives`).
- `-p N`, `--parallel N`: Number of parallel extraction workers (default: 1).
- `--nested`: Recursively extract archives found inside extracted content.
- `--max-depth N`: Maximum nesting depth for `--nested` (default: 10).
- `--type T`: Only process archives of this type (repeatable, e.g. `--type zip --type pst`).
- `--tolerant`: For Outlook `.pst`/`.ost` files, keep the partial output when `readpst` exits with an error but still wrote messages (see the note below). Off by default.
- `-n`, `--dry-run`: Perform a dry run without making any changes.
- `--hard-delete`: Permanently delete source archives instead of quarantining them.
- `--trash-dir PATH`: Use a custom trash directory instead of the default `.pystou-trash/` co-located with the target.
- `--log-dir PATH`: Directory to store log files (default: current directory).
- `--db-dir PATH`: Directory to store index database (default: current directory).

> **Note:** When `--remove-archives` is passed, removed archives are quarantined to `.pystou-trash/` by default.
> Use `pystou restore` to recover them, or `pystou trash purge` to reclaim space.
> Pass `--hard-delete` to permanently delete immediately (old behavior).

> **Outlook PST/OST note:** `readpst` (libpst) sometimes exits with an error on a `.pst`/`.ost` — most
> often a modern Office 365 `.ost` cache — even when it has already extracted most of the mail. By
> default PyStou treats this as a failure: the partial output is discarded and the source archive is
> left in place. Pass `--tolerant` to keep whatever messages `readpst` managed to write (reported with
> a warning). The recovered mail may be incomplete, so `--tolerant` is opt-in.

**Examples:**

- **Interactive Mode:**

  ```bash
  pystou extract /path/to/archives -r
  ```

  *PyStou will prompt you for each archive found.*

- **Automated Mode — Extract and Remove Archives:**

  ```bash
  pystou extract /path/to/archives -r --action extract --remove-archives
  ```

- **Automated Mode — Extract and Keep Archives:**

  ```bash
  pystou extract /path/to/archives -r --action extract --keep-archives
  ```

- **Parallel Extraction (4 workers):**

  ```bash
  pystou extract /path/to/archives -r --action extract --keep-archives -p 4
  ```

- **Nested Extraction (archives inside archives):**

  ```bash
  pystou extract /path/to/archives -r --action extract --remove-archives --nested
  ```

- **Filter by archive type:**

  ```bash
  pystou extract /path/to/archives -r --action extract --type zip --type pst
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
- `--include NAME`: Additional exact file/directory names to remove (repeatable).
- `--list-only`: Only list junk files without removing them.
- `-n`, `--dry-run`: Perform a dry run without making any changes.
- `--hard-delete`: Permanently delete junk files instead of quarantining them.
- `--trash-dir PATH`: Use a custom trash directory instead of the default `.pystou-trash/` co-located with the target.
- `--log-dir PATH`: Directory to store log files (default: current directory).

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

- **Remove additional names:**

  ```bash
  pystou cleanup /path/to/folder -r --include ".gitkeep" --include ".keep"
  ```

### Identify File Types

**Purpose:** Detect file types and find potential issues like mismatched extensions or encrypted archives.

**Command:**

```bash
pystou identify [directory] [options]
```

**Options:**

- `-r`, `--recursive`: Recursively process subdirectories.
- `--check mismatch|encrypted|all`: Which check(s) to run (repeatable). Omit to run all checks.
- `--extensions EXT`: Comma-separated list of extensions to filter on (e.g., `.zip,.pdf`).
- `--log-dir PATH`: Directory to store log files (default: current directory).

**Examples:**

- **Find mismatched extensions:**

  ```bash
  pystou identify /path/to/folder -r --check mismatch
  ```

- **Find encrypted archives:**

  ```bash
  pystou identify /path/to/folder -r --check encrypted
  ```

- **Run all checks:**

  ```bash
  pystou identify /path/to/folder -r --check all
  ```

- **Run multiple checks on specific extensions:**

  ```bash
  pystou identify /path/to/folder -r --check mismatch --check encrypted --extensions ".zip,.pdf,.docx"
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
- `--log-dir PATH`: Directory to store log files (default: current directory).
- `--db-dir PATH`: Directory to store index database (default: current directory).

> Restore never overwrites an occupied path. If the original destination already exists, the item is
> left in the trash and reported as skipped.

**Examples:**

- **Restore a specific run:**

  ```bash
  pystou restore /path/to/folder --run 20260613T142501Z-9f3a
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
- `--log-dir PATH`: Directory to store log files (default: current directory).

**Examples:**

- **Purge a specific run:**

  ```bash
  pystou trash purge /path/to/folder --run 20260613T142501Z-9f3a
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

### Doctor

**Purpose:** Check that all required external tools (`readpst`, `zstd`, `7z`) are installed and accessible on your `PATH`.

**Command:**

```bash
pystou doctor [options]
```

**Options:**

- `--json`: Output results in JSON format.

**Examples:**

- **Check tool availability:**

  ```bash
  pystou doctor
  ```

- **Check as JSON (for scripting):**

  ```bash
  pystou doctor --json
  ```

---

## Migrating from 0.x

PyStou 0.3.0 replaces the argparse-based CLI of earlier (0.2.x) releases with [Typer](https://typer.tiangolo.com/), resulting in a cleaner, more consistent interface. Several flags changed shape.

### Flag Changes

| Command | Old flag (≤0.2.x) | 0.3.0 flag |
|---------|-----------|------------|
| `dedup` | `-c 1` | `--action delete` |
| `dedup` | `-c 2` | `--action merge` |
| `dedup` | `-c 3` | `--action skip` |
| `extract` | `-c 1` | `--action extract` |
| `extract` | `-c 2` | `--action skip` |
| `extract` | `-dc 1` | `--remove-archives` |
| `extract` | `-dc 2` | `--keep-archives` |
| `extract` | `-N` | `--nested` |
| `identify` | `--check-mismatch` | `--check mismatch` |
| `identify` | `--check-encrypted` | `--check encrypted` |
| `identify` | `--check-all` | `--check all` |

### Behavior Notes

- **Quarantine by default**: `cleanup`, `dedup`, and `extract` quarantine removed items to `.pystou-trash/` instead of permanently deleting them. Pass `--hard-delete` to permanently delete immediately (old behavior).
- **New commands**: `pystou restore` and `pystou trash list/purge` manage quarantined files.
- **`pystou doctor`**: checks external tool availability (`readpst`/`zstd`/`7z`). Use it after installation or in CI.
- **Shell completion**: Run `pystou --install-completion` to enable tab-completion for your shell.

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
