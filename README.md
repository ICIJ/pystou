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
  - [Unarchive Files](#unarchive-files)
- [Running Tests](#running-tests)
- [License](#license)

## Features

- Automatically identify and manage duplicate directories, ensuring you only keep what you need.
- Effortlessly extract a wide range of archive formats, including `.zip`, `.tar.gz`, `.zst`, and `.pst`.
- Support for split ZIP archives (`.z01`, `.z02`, etc.) with automatic detection.
- Parallel archive extraction for faster processing of multiple archives.
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

PyStou provides a unified command-line interface with two subcommands: `dedup` and `unarchive`.

```bash
pystou --help
pystou dedup --help
pystou unarchive --help
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

### Unarchive Files

**Purpose:** Extract various archive formats efficiently and manage them post-extraction.

**Supported Formats:**
- Standard: `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz`, `.gz`, `.bz2`
- Zstandard: `.zst`, `.tar.zst`, `.tzst`
- Outlook: `.pst`
- Split ZIP: `.z01`, `.z02`, ... (automatically detected with main `.zip` file)

**Command:**

```bash
pystou unarchive [directory] [options]
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
- `-n`, `--dry-run`: Perform a dry run without making any changes.
- `--log-dir LOG_DIR`: Directory to store log files (default: current directory).
- `--db-dir DB_DIR`: Directory to store index database (default: current directory).

**Examples:**

- **Interactive Mode:**

  ```bash
  pystou unarchive /path/to/archives -r
  ```

  *The script will prompt you for each archive found, asking whether to extract or skip.*

- **Automated Mode with Default Choices (Extract and Delete Archives):**

  ```bash
  pystou unarchive /path/to/archives -r -c 1 -dc 1
  ```

- **Parallel Extraction (4 workers):**

  ```bash
  pystou unarchive /path/to/archives -r -c 1 -dc 2 -p 4
  ```

- **Dry Run Mode:**

  ```bash
  pystou unarchive /path/to/archives -r -n
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
