# 🌿 PyStou

Welcome to **PyStou** – your ultimate toolkit for keeping your filesystem tidy and organized! Whether you're a developer drowning in duplicate folders or someone who loves archiving files but hates the clutter, PyStou is here to rescue you from chaos with style and efficiency.

**PyStou** is proudly developed by the [International Consortium of Investigative Journalists (ICIJ)](https://www.icij.org/), aiming to empower users with tools to manage and maintain large amounts of files.

## 📚 Table of Contents

- [📚 Table of Contents](#-table-of-contents)
- [✨ Features](#-features)
- [🚀 Installation](#-installation)
  - [Prerequisites](#prerequisites)
  - [Clone the Repository](#clone-the-repository)
  - [Install the Package](#install-the-package)
- [🔧 Usage](#-usage)
  - [Deduplicate Folders](#deduplicate-folders)
  - [Unarchive Files](#unarchive-files)
- [🧪 Running Tests](#-running-tests)
- [🤝 Contributing](#-contributing)
  - [How to Contribute](#how-to-contribute)
  - [Guidelines](#guidelines)
- [📄 License](#-license)

## ✨ Features

- **Deduplicate Folders:** Automatically identify and manage duplicate directories, ensuring you only keep what you need.
- **Unarchive Files:** Effortlessly extract a wide range of archive formats, including `.zip`, `.tar.gz`, `.zst`, and `.pst`.
- **Interactive & Automated Modes:** Choose to interact with each file/archive or set default actions for seamless automation.
- **Dry Run Mode:** Preview actions without making any changes – perfect for cautious users!
- **Comprehensive Logging:** Keep track of all actions with detailed JSON-formatted logs for easy troubleshooting.
- **No External Dependencies:** Pure Python scripts ready to run out-of-the-box (except for necessary command-line tools like `readpst`).

## 🚀 Installation

Getting started with PyStou is a breeze! Follow the steps below to install and set up the project on your machine.

### Prerequisites

- **Python 3.6 or higher** is required.
- **Command-Line Tools:**
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

## 🔧 Usage

PyStou comes with two main scripts: `dedup_folders` and `unarchive`. Both scripts are accessible via the command line once installed.

### Deduplicate Folders

**Purpose:** Identify and manage duplicate directories to keep your filesystem clean.

**Command:**

```bash
dedup_folders [directory] [options]
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
- `--dry-run`: Perform a dry run without making any changes.
- `--log-dir LOG_DIR`: Directory to store log files (default: current directory).
- `--db-dir DB_DIR`: Directory to store index database (default: current directory).

**Examples:**

- **Interactive Mode:**

  ```bash
  dedup_folders /path/to/your/folders -r
  ```

  *The script will prompt you for each duplicate group found.*

- **Automated Mode with Default Choice (Delete Duplicates):**

  ```bash
  dedup_folders /path/to/your/folders -r -c 1
  ```

- **Dry Run Mode:**

  ```bash
  dedup_folders /path/to/your/folders -r --dry-run
  ```

### Unarchive Files

**Purpose:** Extract various archive formats efficiently and manage them post-extraction.

**Command:**

```bash
unarchive [directory] [options]
```

**Parameters:**

- `directory`: (Optional) The root directory to start searching for archives. Defaults to the current directory if not specified.

**Options:**

- `-r`, `--recursive`: Recursively search subdirectories for archives.
- `-c CHOICE`, `--default-choice CHOICE`: Default action to apply to all archives.
  - `1`: Extract archives.
  - `2`: Skip (do nothing).
  - `3`: Delete archives.
- `-dc DELETE_CHOICE`, `--default-delete-choice DELETE_CHOICE`: Default action when prompted to delete archives after extraction.
  - `1`: Delete the archive after extraction.
  - `2`: Keep the archive after extraction.
- `--dry-run`: Perform a dry run without making any changes.
- `--log-dir LOG_DIR`: Directory to store log files (default: current directory).
- `--db-dir DB_DIR`: Directory to store index database (default: current directory).

**Examples:**

- **Interactive Mode:**

  ```bash
  unarchive /path/to/archives -r
  ```

  *The script will prompt you for each archive found, asking whether to extract, skip, or delete.*

- **Automated Mode with Default Choices (Extract and Delete Archives):**

  ```bash
  unarchive /path/to/archives -r -c 1 -dc 1
  ```

- **Dry Run Mode:**

  ```bash
  unarchive /path/to/archives -r --dry-run
  ```

## 🧪 Running Tests

PyStou includes a suite of unit tests to ensure everything works smoothly. Here's how to run them:

1. **Navigate to the Project Root:**

   ```bash
   cd /path/to/pystou
   ```

2. **Run Tests Using `unittest`:**

   ```bash
   python -m unittest discover tests
   ```

> **Note:** Ensure you have all necessary command-line tools installed (`readpst`, `zstd`) before running tests that involve archive extraction.

## 🤝 Contributing

We love contributions! Whether it's reporting bugs, suggesting features, or submitting pull requests, your help is invaluable.

### How to Contribute

1. **Fork the Repository:**

   Click the "Fork" button at the top-right corner of the repository page.

2. **Clone Your Fork:**

   ```bash
   git clone https://github.com/yourusername/pystou.git
   cd pystou
   ```

3. **Create a New Branch:**

   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **Make Your Changes:**

   Implement your feature or fix.

5. **Commit Your Changes:**

   ```bash
   git commit -m "Add your descriptive commit message"
   ```

6. **Push to Your Fork:**

   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create a Pull Request:**

   Navigate to your fork on GitHub and click the "Compare & pull request" button.

### Guidelines

- **Commit Messages:** Follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification for clear and consistent commit messages.
- **Code Style:** We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting. Ensure your code adheres to PEP 8 standards.
- **Documentation:** Update the README and docstrings as necessary.
- **Testing:** Ensure all new features are accompanied by relevant tests.
- **Code Reviews:** All pull requests will undergo a review process to maintain code quality and integrity.

## 📄 License

Distributed under the [MIT License](LICENSE). See `LICENSE` for more information.