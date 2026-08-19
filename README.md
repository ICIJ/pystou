# PyStou

Command-line toolkit for tidying large filesystems: deduplicate folders, extract archives, remove
junk files, and report on what is taking up space. Removals are reversible by default.

Developed by the [International Consortium of Investigative Journalists (ICIJ)](https://www.icij.org/).

## Install

```bash
pipx install pystou      # isolated environment, recommended
uv tool install pystou   # https://docs.astral.sh/uv/
pip install pystou
```

Requires Python 3.9+. `typer` and `rich` are installed automatically.

Some archive formats need an external tool. Run `pystou doctor` to check which are present:

| Tool | Needed for |
|------|-----------|
| `p7zip-full` | split ZIP archives (`.z01`, `.z02`, ...) |
| `pst-utils` | Outlook `.pst` and `.ost` (`readpst`) |
| `zstd` | `.zst` archives |

From source:

```bash
git clone https://github.com/ICIJ/pystou.git
cd pystou
make install
```

## Quick start

```bash
pystou stats  ~/Downloads -r            # what is in here?
pystou dedup  ~/Downloads -r            # prompt per duplicate group
pystou extract ~/Downloads -r --action extract
pystou cleanup ~/Downloads -r           # drop .DS_Store, Thumbs.db, ...
pystou restore ~/Downloads --all        # undo the above
```

## Commands

| Command | Purpose |
|---------|---------|
| [`dedup`](#dedup) | Find duplicate directories and delete or merge them |
| [`extract`](#extract) | Extract archives, optionally nested and in parallel |
| [`cleanup`](#cleanup) | Remove OS junk files |
| [`identify`](#identify) | Detect extension mismatches and encrypted archives |
| [`stats`](#stats) | Report file counts, sizes, and types |
| [`empty`](#empty) | Find and remove empty directories |
| [`restore`](#restore) | Put quarantined items back |
| [`trash`](#trash) | List or permanently purge quarantined items |
| [`doctor`](#doctor) | Check that external tools are installed |

Every command takes an optional directory (default: current) and `--help`.

## Reversible by default

`cleanup`, `dedup`, and `extract` never delete: they move items into a `.pystou-trash/` directory
next to the target. Use `pystou restore` to undo and `pystou trash purge` to reclaim the space.
`pystou trash purge` is the only command that truly deletes data.

Pass `--hard-delete` to delete immediately instead.

## Global options

These go **before** the subcommand name.

| Flag | Description |
|------|-------------|
| `--no-color` | Disable colored output (piping, CI). |
| `-q`, `--quiet` | Suppress progress bars and status messages; errors only. |
| `--version` | Print the installed version and exit. |
| `--install-completion` | Install shell completion (bash, zsh, fish). |
| `--show-completion` | Print the completion script. |

```bash
pystou --no-color dedup /data -r
pystou --quiet extract /data -r --action extract
```

## Shared options

| Flag | Description | Available on |
|------|-------------|--------------|
| `-r`, `--recursive` | Recurse into subdirectories. | `dedup` `extract` `cleanup` `identify` `stats` `empty` |
| `-n`, `--dry-run` | Do not make any changes. | `dedup` `extract` `cleanup` `empty` |
| `--hard-delete` | Permanently delete instead of quarantining. | `dedup` `extract` `cleanup` |
| `--trash-dir PATH` | Override the trash location (must be the same filesystem). | `dedup` `extract` `cleanup` `restore` `trash` |
| `--log-dir PATH` | Directory for JSON log files (default: current). | all but `doctor` |
| `--db-dir PATH` | Directory for the index database (default: current). | `dedup` `extract` `restore` |

## Command reference

### dedup

Identify duplicate directories and delete or merge them.

```bash
pystou dedup [directory] [options]
```

| Option | Description |
|--------|-------------|
| `-l`, `--level N` | Maximum recursion depth. |
| `--action delete\|merge\|skip` | Apply to every duplicate group; omit to prompt per group. |

```bash
pystou dedup /data -r                    # prompt per group
pystou dedup /data -r --action delete    # keep one copy of each
pystou dedup /data -r --action merge     # merge contents, then quarantine
```

### extract

Extract archives and optionally clean up the sources.

```bash
pystou extract [directory] [options]
```

Each archive is extracted into its own directory beside it, named after the archive
(`photos.zip` -> `photos/`). If that name is taken, a numbered one is used (`photos (1)/`), so
extracting never overwrites existing files.

**Supported formats:** `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz`, `.gz`, `.bz2`,
`.zst`, `.tar.zst`, `.tzst`, `.pst`, `.ost`, and split ZIP (`.z01`, `.z02`, ... detected from the
main `.zip`).

| Option | Description |
|--------|-------------|
| `--action extract\|skip` | Apply to every archive; omit to prompt per archive. |
| `--remove-archives` / `--keep-archives` | Quarantine source archives after success, or keep them (default: keep). |
| `-p`, `--parallel N` | Parallel extraction workers (default: 1). |
| `--nested` | Recursively extract archives found in extracted content. |
| `--max-depth N` | Maximum nesting depth for `--nested` (default: 10). |
| `--type T` | Only process this archive type (repeatable). |
| `--tolerant` | Keep partial `.pst`/`.ost` output when `readpst` fails (see below). |

```bash
pystou extract /data -r --action extract --remove-archives
pystou extract /data -r --action extract -p 4 --nested
pystou extract /data -r --action extract --type zip --type pst
```

> **Outlook PST/OST:** `readpst` sometimes exits with an error, most often on a modern Office 365
> `.ost` cache, after already extracting most of the mail. By default PyStou treats that as a
> failure: the partial output is discarded and the archive is left in place. `--tolerant` keeps
> whatever messages were written and reports a warning. The recovered mail may be incomplete, which
> is why it is opt-in.

### cleanup

Remove junk files created by operating systems and applications.

```bash
pystou cleanup [directory] [options]
```

Removed by default:

- **macOS:** `.DS_Store`, `._.DS_Store`, `._*`, `__MACOSX`, `.AppleDouble`, `.Spotlight-V100`, `.Trashes`, `.fseventsd`, `.TemporaryItems`, `.LSOverride`
- **Windows:** `Thumbs.db`, `ehthumbs.db`, `ehthumbs_vista.db`, `desktop.ini`

| Option | Description |
|--------|-------------|
| `--include NAME` | Additional exact file/directory name to remove (repeatable). |
| `--list-only` | List junk files without removing them. |

```bash
pystou cleanup /data -r --list-only
pystou cleanup /data -r --include ".gitkeep" --include ".keep"
```

### identify

Detect file types and flag mismatched extensions or encrypted archives.

```bash
pystou identify [directory] [options]
```

| Option | Description |
|--------|-------------|
| `--check mismatch\|encrypted\|all` | Which check to run (repeatable). Omit to run all. |
| `--extensions EXT` | Comma-separated extensions to filter on (e.g. `.zip,.pdf`). |

```bash
pystou identify /data -r --check encrypted
pystou identify /data -r --check mismatch --extensions ".zip,.pdf,.docx"
```

### stats

Report on files and directories.

```bash
pystou stats [directory] [options]
```

| Option | Description |
|--------|-------------|
| `--top N` | Number of top items to show (default: 10). |
| `--by-extension` | Break down by file extension. |
| `--by-size` | Show largest files. |
| `--json` | Output as JSON. |

```bash
pystou stats /data -r --by-size --top 20
pystou stats /data -r --json
```

### empty

Find and remove empty directories.

```bash
pystou empty [directory] [options]
```

| Option | Description |
|--------|-------------|
| `--list-only` | List empty directories without removing them. |
| `--include-hidden` | Include hidden directories (starting with `.`). |

```bash
pystou empty /data -r --list-only
pystou empty /data -r --include-hidden
```

### restore

Move quarantined items back to their original locations.

```bash
pystou restore [directory] [options]
```

| Option | Description |
|--------|-------------|
| `--run ID` | Restore one quarantine run (find IDs with `pystou trash list`). |
| `--all` | Restore every item across all runs. |
| `--path ORIGINAL` | Restore a single item by its original absolute path. |

```bash
pystou restore /data --run 20260613T142501Z-9f3a
pystou restore /data --all
pystou restore /data --path /data/old-file.zip
```

> Restore never overwrites an occupied path. If the original destination exists, the item stays in
> the trash and is reported as skipped.

### trash

```bash
pystou trash list  [directory] [--json]
pystou trash purge [directory] [options]
```

`list` shows every quarantine run with its item count and reclaimable space. `purge` permanently
deletes; there is no undo.

| `purge` option | Description |
|--------|-------------|
| `--run ID` | Purge one run. |
| `--all` | Purge every run. |
| `--older-than DAYS` | Purge runs at least DAYS old. |

```bash
pystou trash list /data
pystou trash purge /data --older-than 30
```

### doctor

Check that `readpst`, `zstd`, and `7z` are installed and on your `PATH`.

```bash
pystou doctor [--json]
```

## Migrating from 0.x

0.3.0 replaced the argparse CLI of 0.2.x with [Typer](https://typer.tiangolo.com/).

| Command | Old flag (<=0.2.x) | Now |
|---------|--------------------|-----|
| `dedup` | `-c 1` / `-c 2` / `-c 3` | `--action delete` / `merge` / `skip` |
| `extract` | `-c 1` / `-c 2` | `--action extract` / `skip` |
| `extract` | `-dc 1` / `-dc 2` | `--remove-archives` / `--keep-archives` |
| `extract` | `-N` | `--nested` |
| `identify` | `--check-mismatch` / `--check-encrypted` / `--check-all` | `--check mismatch` / `encrypted` / `all` |

Behavior changes:

- `cleanup`, `dedup`, and `extract` quarantine instead of deleting. `--hard-delete` restores the old behavior.
- New commands: `pystou restore`, `pystou trash list`, `pystou trash purge`, `pystou doctor`.
- `pystou --install-completion` enables shell tab-completion.

## Development

```bash
make install    # sync the environment with dev extras
make test
make lint
make typecheck
```

Archive extraction tests need `readpst`, `zstd`, and `7z` on your `PATH`.

## License

[MIT](LICENSE).
