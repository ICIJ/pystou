# CHANGELOG


## v0.7.0 (2026-08-21)

### Chores

- Sync uv.lock with the released version
  ([`312fcf5`](https://github.com/ICIJ/pystou/commit/312fcf5392f5e02b651b1e90f12d74d72d006857))

### Features

- **normalize**: Add the astral rule to strip characters above the BMP
  ([`08aadfa`](https://github.com/ICIJ/pystou/commit/08aadfad0510a55efb0fd809e5cfe04fd1a8ff81))


## v0.6.0 (2026-08-20)

### Bug Fixes

- **cli**: Create the directory named by --log-dir
  ([`add47ae`](https://github.com/ICIJ/pystou/commit/add47ae83c2b9e2cbe4f9b1274c5a49f128eae06))

- **index**: Reject and explain paths the index cannot store
  ([`18580e8`](https://github.com/ICIJ/pystou/commit/18580e8d1a06cbe420df36ba4122bccce20462af))

- **normalize**: Credit the trim that punctuation removal exposes
  ([`920a6c6`](https://github.com/ICIJ/pystou/commit/920a6c649aa8cb422c6c4d467073227aaa710ba5))

- **normalize**: Drop the same-inode short circuit that faked a rename
  ([`577c5fa`](https://github.com/ICIJ/pystou/commit/577c5fad33f16c6a532cee26f2448aa4375b9d74))

- **normalize**: Honor --dry-run when combined with --undo
  ([`347a152`](https://github.com/ICIJ/pystou/commit/347a15247097f11cbc398198790d89dcd8464746))

- **normalize**: Record absolute paths and stop rewriting valid names
  ([`991d7be`](https://github.com/ICIJ/pystou/commit/991d7be5b119ff9441df83da45cbe1e013c15c09))

- **normalize**: Release the reserved name when a rename fails
  ([`2585740`](https://github.com/ICIJ/pystou/commit/25857409827156559a4c1c55c0c7dba474bcf24a))

- **normalize**: Resolve all renamed ancestors, not just the first, in dry-run undo
  ([`0fe7f72`](https://github.com/ICIJ/pystou/commit/0fe7f72f944642dcec448ae6966eef0390b1adae))

- **normalize**: Write the manifest only once there is a rename to record
  ([`2c27e3a`](https://github.com/ICIJ/pystou/commit/2c27e3a12f47946ad86ef33dfcb4a009923d2983))

### Chores

- Sync uv.lock with the released version
  ([`fabb3c5`](https://github.com/ICIJ/pystou/commit/fabb3c5155c62cc57de1edadb693a8b48ad0b690))

### Documentation

- **normalize**: Document the options and the manifest location
  ([`f43a687`](https://github.com/ICIJ/pystou/commit/f43a6877d05478c703f8eb7be9c0f9a46d12ca0c))

### Features

- **normalize**: Add --no-manifest to rename without recording
  ([`52cfe09`](https://github.com/ICIJ/pystou/commit/52cfe098a8c70695e23696d730f46687a9fb4aae))

- **normalize**: Add filename normalization rules
  ([`8b0e331`](https://github.com/ICIJ/pystou/commit/8b0e3318ba1a2017641d6d179bdee09d68d0dd91))

- **normalize**: Add the JSONL rename manifest
  ([`3e8c5f6`](https://github.com/ICIJ/pystou/commit/3e8c5f6f49eb60b6fc25348da7bda7be80269749))

- **normalize**: Add the normalize subcommand
  ([`ce87aea`](https://github.com/ICIJ/pystou/commit/ce87aea260bf4ce582c9626090755eabcef67fcb))

- **normalize**: Document the command and pin the undo round-trip
  ([`c0270f8`](https://github.com/ICIJ/pystou/commit/c0270f854479df54ae9397a8b2c9d92f7439fc7a))

- **normalize**: Undo a rename run from its manifest
  ([`c8fed2b`](https://github.com/ICIJ/pystou/commit/c8fed2b0e8758c41b84c648dd28ba667a23ecd2e))

- **safe-ops**: Keep the file extension when suffixing unique names
  ([`3819321`](https://github.com/ICIJ/pystou/commit/3819321adb7b8721b9492d8146fbd9aa55bb9c34))


## v0.5.0 (2026-08-19)

### Chores

- Remove dead helpers from common
  ([`3065bf1`](https://github.com/ICIJ/pystou/commit/3065bf1d62c13f8a283793175fa7ec9e25094dbb))

log_configuration, prompt_use_existing_index, load_directories_from_index, summarize_group,
  get_directory_size, unique_path, verify_then_delete and the extract_pst_archive alias had no
  production callers. Tests that only exercised them are gone; tests that used them as query helpers
  now query directly.

### Continuous Integration

- Run make typecheck now that the repo type-checks clean
  ([`8abdde3`](https://github.com/ICIJ/pystou/commit/8abdde32f558cc20e14de5daebf2980af8284911))

### Documentation

- Reorganize the README into a shorter command reference
  ([`6424bd5`](https://github.com/ICIJ/pystou/commit/6424bd5bcefa6d300a8aaed395e4a0748486cb0c))

- Restore the original README intro
  ([`7abe595`](https://github.com/ICIJ/pystou/commit/7abe5957e2c8c50165e826f6f49ce38104c97515))

### Features

- **cli**: Store logs and indexes in XDG base directories
  ([`e944d65`](https://github.com/ICIJ/pystou/commit/e944d65f2eeb76996564c8809891176097ee7fd2))

### Refactoring

- **common**: Share the index bootstrap via open_or_rescan
  ([`2c67e48`](https://github.com/ICIJ/pystou/commit/2c67e4885988a5ee8270ac374a4fedf1cb22eb94))

extract and dedup carried the same db_path/initialize_database/rescan-closure block; the only
  difference was dedup passing a depth level, now a parameter. restore and initialize_database spell
  the db filename via indexer.DB_NAME.

- **common**: Unify byte-size formatting on console.human_size
  ([`06ff1b1`](https://github.com/ICIJ/pystou/commit/06ff1b179dc4cd9a6c54ad0166ae70e6965cdf96))

stats rendered '1.0 KB' up to PB while trash rendered '1.0KB' and capped at TB, so a >1 PB trash run
  showed as '2048.0TB'. Both now share the spaced, PB-aware formatter; its tests move to
  tests/test_console.py and cover the PB case.

- **trash**: Drop the unused dry_run branch from quarantine
  ([`16f46d9`](https://github.com/ICIJ/pystou/commit/16f46d9fcd442667102c9207e83a0e0832d33d0a))

All three callers (cleanup, dedup, extract) short-circuit on dry run before reaching quarantine, so
  the parameter was never passed outside its own test.


## v0.4.1 (2026-08-19)

### Bug Fixes

- **cleanup**: Apply --include patterns to junk directories
  ([`91e84e8`](https://github.com/ICIJ/pystou/commit/91e84e81441acab03b8d18bda0405c8cc5254ec8))

--include documented extra file/dir names but only extended the junk file set, so a directory name
  passed to it was never matched.

- **cleanup**: Report quarantine OSError instead of aborting the run
  ([`18c157a`](https://github.com/ICIJ/pystou/commit/18c157ae759a5ce92d323615612c438ffea0f71d))

A PermissionError from os.rename escaped remove_junk and crashed the command after part of the batch
  had already been moved and ledgered.

- **cli**: Drop --db-dir from commands that never open the index
  ([`93b4c48`](https://github.com/ICIJ/pystou/commit/93b4c48b802682c14e658a40c6ecac4b22576c5b))

cleanup, empty, identify and stats accepted and documented --db-dir but never referenced it, so
  pointing it anywhere had no effect.

- **dedup**: Index merged subdirectories as directories
  ([`285c915`](https://github.com/ICIJ/pystou/commit/285c915590530b1b26247e1fa61a81dd1c3c3fc1))

merge_contents moves whatever os.listdir yields, so a moved subdirectory was recorded as a zero-size
  file and its contents disappeared from the index.

- **dedup**: Only group a suffixed directory next to its plain base
  ([`abfea39`](https://github.com/ICIJ/pystou/commit/abfea3966d800d1fad3a1e214b9bc2830de2d690))

'Trip (2019)' and 'Trip (2020)' were treated as copies of 'Trip' and one of them was deleted.

- **dedup**: Scope duplicate grouping to the operation root
  ([`90c1493`](https://github.com/ICIJ/pystou/commit/90c14937a6aa09ed169e5f6c2043d5fb504dac89))

A stale index built from another tree made dedup delete or quarantine directories the user never
  named.

- **dedup**: Take the base directory from the group key
  ([`2220932`](https://github.com/ICIJ/pystou/commit/22209322982297f3e25086a7bf087e9db8fe1a2a))

identify_base_and_duplicates re-parsed the ' (n)' convention with two regexes and returned
  float('inf') from an int-annotated helper; the base name the grouping already produced identifies
  the base directory.

- **empty**: Count hidden files as directory content
  ([`218109c`](https://github.com/ICIJ/pystou/commit/218109cd34673710dcf91c1de692d69c1cfdc4e1))

is_directory_empty ignored hidden entries unless --include-hidden was set, so a directory holding
  only a .DS_Store was listed as empty and then failed to rmdir. The flag governs which directories
  are traversed and removed, not what counts as content.

- **empty**: Count symlink entries as directory content
  ([`e4d6979`](https://github.com/ICIJ/pystou/commit/e4d6979c5ac29aaae027c628d80deb4687dc4c3c))

A directory whose only entry was a symlink was reported as empty and then failed to rmdir with
  ENOTEMPTY, the same flaw as the hidden-file case.

- **empty**: Detect ENOTEMPTY by errno instead of message text
  ([`62a7fc3`](https://github.com/ICIJ/pystou/commit/62a7fc35c48068763df19f50dc1def02c0fb60f7))

The hardcoded 39 is Linux-only (macOS/BSD use 66) and the strerror substring is localized, so a
  benign non-empty directory was escalated to an error under a non-English locale.

- **extract**: Discover archives whose extension is uppercased
  ([`b65caae`](https://github.com/ICIJ/pystou/commit/b65caae3afbcc82b7d14c2feaa8c0e602d01ce5c))

- **extract**: Dispatch and name output on the case-folded suffix
  ([`63e1001`](https://github.com/ICIJ/pystou/commit/63e1001798da1b3813d6efe5936d91c957294e16))

- **extract**: Extract each nested archive at most once
  ([`1dc6c9f`](https://github.com/ICIJ/pystou/commit/1dc6c9f0cedc823135b383039f7591f6e3c277c5))

- **extract**: Extract TAR.ZST archives into a unique directory
  ([`bb9aa10`](https://github.com/ICIJ/pystou/commit/bb9aa1022420872e10e28a08f0b1092703440f25))

- **extract**: Extract ZIP and TAR archives into a unique directory
  ([`86abaab`](https://github.com/ICIJ/pystou/commit/86abaabfb24e9f6aeb46accdcee90bdb06d765a2))

- **extract**: Harden the 7z, zstd and readpst invocations
  ([`40734b6`](https://github.com/ICIJ/pystou/commit/40734b6aa23ed55a1cda82a8616ce362abcfdd50))

- **extract**: Honour --max-depth on the parallel nested path
  ([`ed7ed5e`](https://github.com/ICIJ/pystou/commit/ed7ed5e7bf4bf61ba1dfb12e4bfc074372b90745))

- **extract**: Keep a corrupt archive from aborting the whole run
  ([`36de5d4`](https://github.com/ICIJ/pystou/commit/36de5d4ad3671ab51105816dd1230e9118629440))

- **extract**: Prune the trash directory when discovering archives
  ([`484b2c7`](https://github.com/ICIJ/pystou/commit/484b2c7bf0e33269df3b86ae02a37ec8db3de220))

- **extract**: Reject an unknown --type instead of matching nothing
  ([`a8fa29b`](https://github.com/ICIJ/pystou/commit/a8fa29bb11f232823f1151aff2a2d36940e40a7a))

- **extract**: Remove the output directory when extraction fails unexpectedly
  ([`b5179e2`](https://github.com/ICIJ/pystou/commit/b5179e2546a2d5df381ca9a947805389e516eca8))

- **extract**: Update the index incrementally instead of clearing it
  ([`028d190`](https://github.com/ICIJ/pystou/commit/028d190d3544beb6a75e39f5a118d77c98145fe2))

- **identify**: Stop matching tar magic at byte 0
  ([`f5ff004`](https://github.com/ICIJ/pystou/commit/f5ff004c7178d4389a273a80daeaa3f1f867974f))

The 'ustar' entry was matched with header.startswith while the real magic lives at offset 257, and
  the offset probe short-circuited ahead of every genuine header signature.

- **identify**: Strip --extensions tokens before the leading-dot check
  ([`6fa024b`](https://github.com/ICIJ/pystou/commit/6fa024bc5ea0af551ac05b90513409eea71f5b8c))

' .pdf' was tested unstripped, so a space after the comma produced '..pdf' and silently filtered out
  every matching file.

- **indexer**: Make (directory_path, name) unique in the files table
  ([`c84dd76`](https://github.com/ICIJ/pystou/commit/c84dd768bf63b897b1ef1966d2ed512320942248))

Without it every INSERT OR IGNORE added a row, so re-indexing a file multiplied the size and file
  count shown for its directory. Existing databases get the constraint through a unique index,
  dropping the duplicate rows they already hold.

- **restore**: Search every run when only --path is given
  ([`f887840`](https://github.com/ICIJ/pystou/commit/f887840ef172cf4596bc3d5eda9acface6f16d8b))

--path alone selected no run at all, so the CLI reported 'Restored 0 item(s).' and exited 0 while
  the item stayed in the trash.

- **safe-extract**: Resolve symlinks when checking member containment
  ([`0041fda`](https://github.com/ICIJ/pystou/commit/0041fda3057f8ac64cb90156aaa90619dd8d9643))

- **stats**: Reject a negative --top
  ([`aec8d97`](https://github.com/ICIJ/pystou/commit/aec8d9701db0f5c764f83ce2ed73ef44e0ac2fc7))

A negative bound sliced the tables from the end and printed titles like 'Top -5 Extensions by
  Count'.

- **stats**: Survive --top 0
  ([`ec12425`](https://github.com/ICIJ/pystou/commit/ec12425f5d8d4909a71f9fc99fc0672492bacdcb))

With top_n <= 0 the first file fell through to the size comparison and indexed the still-empty heap.

- **trash**: Name the searched trash root when nothing is found
  ([`c4e2598`](https://github.com/ICIJ/pystou/commit/c4e25989ec5fe8cddc13914b7579a0a46a9f2933))

A run made with --trash-dir left 'Trash is empty.' and a silent 'Restored 0 item(s).' behind; the
  ledger header now records the trash root too.

- **trash**: Never re-quarantine items already inside the trash root
  ([`1272b75`](https://github.com/ICIJ/pystou/commit/1272b75b596157dbf69ac62f03b6e720537e4053))

A --trash-dir inside the scanned tree is walked as ordinary data, so a second run moved run 1's own
  items and left its ledger dangling.

- **trash**: Reject ledger run ids that escape the trash root
  ([`3958e55`](https://github.com/ICIJ/pystou/commit/3958e550e555da3c38d353cd1c8e831c54cc6b59))

A ledger planted inside the trash tree could carry a run_id like '../../victim'; purge joined it
  onto the trash root and rmtree'd it.

- **trash**: Treat --older-than as a purge selector on its own
  ([`bef28e0`](https://github.com/ICIJ/pystou/commit/bef28e072086fb2902f8bde18ffa1862864a88c5))

'pystou trash purge DIR --older-than 30' matched the safety gate before the age filter ran, so the
  documented command was a silent no-op.

- **trash**: Validate ledger paths before restoring them
  ([`0f2ef37`](https://github.com/ICIJ/pystou/commit/0f2ef3777d31d744a3c2df62f77ad730f36184b6))

An absolute 'stored' silently discarded the trash root and 'original' was never checked against the
  run's op_root, so a planted ledger could move files in and out of arbitrary locations.

- **types**: Make the unique-name helpers and prompt_choice type-check
  ([`4aaf55b`](https://github.com/ICIJ/pystou/commit/4aaf55b2c85ad081d332edf8ec5f2d27448e2b4a))

The candidate loops fell off the end of a Path-returning function and prompt_choice accepted a None
  default no caller passes.

### Build System

- Derive the lint and typecheck package list from the tree
  ([`654d2f0`](https://github.com/ICIJ/pystou/commit/654d2f0b3ec07dd64241f6a6a071c0e2eb450397))

The hardcoded SRC list had drifted and excluded doctor, restore and trash.

- Raise the mypy target to 3.10
  ([`0834b96`](https://github.com/ICIJ/pystou/commit/0834b961a8493e3a84f08e3d104be393717ebee4))

mypy 2.x rejects python_version = "3.9" and silently falls back to its default, warning on every
  run.

### Chores

- Pin python and uv with mise
  ([`f70ef1d`](https://github.com/ICIJ/pystou/commit/f70ef1d6445022d7176b94d4c91f746fbaadf2ee))

- **stats**: Type the stats accumulator for mypy
  ([`69b6d06`](https://github.com/ICIJ/pystou/commit/69b6d06091cd6869c94c6d304050cd1854d43152))

The heterogeneous dict literal widened to object, which made every stats[...] access an error.

### Code Style

- Apply ruff format to the touched tests
  ([`26c0e77`](https://github.com/ICIJ/pystou/commit/26c0e776c82d762c05df8142e06a0d0d7585f31c))

- **indexer**: Let ruff format the unique-index statement
  ([`29079ef`](https://github.com/ICIJ/pystou/commit/29079efcc2d52b6e7d5abc1461f5d476cdebe6a2))

### Continuous Integration

- Keep the typecheck step out until the existing errors are fixed
  ([`e4b07cf`](https://github.com/ICIJ/pystou/commit/e4b07cf113ca8a5a351b130c7f98842ff57dfe92))

make typecheck currently reports 32 pre-existing errors in packages this branch does not touch. The
  step lands with the branch that fixes them.

- Run make lint and add a typecheck step
  ([`c5a55c0`](https://github.com/ICIJ/pystou/commit/c5a55c0f79c02223a8ff458d9e63db75bcae2561))

The lint job repeated a truncated package list and mypy never ran.

### Documentation

- Correct run-id format, --include semantics and --db-dir scope
  ([`ebeb771`](https://github.com/ICIJ/pystou/commit/ebeb771bad2fef084c3840c0251e50ce1274057c))

Run ids are minted as %Y%m%dT%H%M%SZ plus a random suffix, --include matches exact names rather than
  globs, and cleanup and identify never open the index database.

### Performance Improvements

- **identify**: Read each candidate file once
  ([`8a2bc7b`](https://github.com/ICIJ/pystou/commit/8a2bc7b44baf2a4380b4bfcae64a81b5729fbd5e))

The tar probe re-opened every file to seek to 257; a single 262-byte read covers both the header
  signatures and the tar magic.

- **trash**: Stop rescanning taken holding dirs on every quarantined item
  ([`8f3e8e9`](https://github.com/ICIJ/pystou/commit/8f3e8e9c668046205c7ec3a2bbd190da9fc7c2b4))

reserve_unique_name restarted its probe at 0 for each item, so a run of n items issued n(n+1)/2
  mkdir calls; the caller now carries the counter.

### Refactoring

- **extract**: Call delete_archive_file directly on the parallel path
  ([`52d2702`](https://github.com/ICIJ/pystou/commit/52d2702335cb9fd5a734384590efcbbfaf625c8f))

- **utils**: Share one canonical archive extension list with stats
  ([`63558cc`](https://github.com/ICIJ/pystou/commit/63558cc8905744c4025ea7b505cb744a74f501c3))

### Testing

- **empty**: Cover the symlink guard in remove_empty_directories
  ([`e422853`](https://github.com/ICIJ/pystou/commit/e422853b9316e13d28595215a1a8b02a0834a3ac))


## v0.4.0 (2026-06-15)

### Bug Fixes

- **extract**: Handle readpst non-zero exits on PST/OST with --tolerant
  ([`4df808f`](https://github.com/ICIJ/pystou/commit/4df808f3b3fdfc2f2f660377ba8c1323e29cefdc))

- **packaging**: Include doctor package in the wheel
  ([`9636053`](https://github.com/ICIJ/pystou/commit/963605378b5e1c4f55d65ea05a7c0b4103ebaeb7))

### Code Style

- **extract**: Unwrap readpst message to satisfy ruff format
  ([`a7b46d0`](https://github.com/ICIJ/pystou/commit/a7b46d0495f64a128ebb9ec357c843cf9acd9822))

### Documentation

- Align CHANGELOG OST entry with conventional-changelog style
  ([`608fa2e`](https://github.com/ICIJ/pystou/commit/608fa2ea20bcd3c601d9498c2688d483247c1f19))

- Document OST file support
  ([`6352c41`](https://github.com/ICIJ/pystou/commit/6352c419d4e0ad51536dcc9f1ba4907eed6f27bf))

### Features

- **extract**: Discover .ost files and support --type ost
  ([`277df01`](https://github.com/ICIJ/pystou/commit/277df01ca05b33ddfb88713cee980309c45a01d7))

- **extract**: Extract OST files via readpst (shared Outlook extractor)
  ([`022a7a1`](https://github.com/ICIJ/pystou/commit/022a7a12d4787b710c77396a01bd2c6513d91f71))

- **identify**: Recognize .ost files (shared PST signature)
  ([`cc8f677`](https://github.com/ICIJ/pystou/commit/cc8f677e6388428b0597ddcb30ae8338966e4218))

### Refactoring

- **extract**: Derive action and label from suffix directly
  ([`1896ce3`](https://github.com/ICIJ/pystou/commit/1896ce3dd21ebf2c0dd9998c1bbcbc2a1e7718a3))


## v0.3.1 (2026-06-13)

### Bug Fixes

- **doctor**: Show clean version numbers for 7z and zstd
  ([`c3be476`](https://github.com/ICIJ/pystou/commit/c3be47650e7c273a70378ece8fbc32daeae4fe5f))

### Chores

- **deps**: Sync uv.lock with typer and rich
  ([`716bfdc`](https://github.com/ICIJ/pystou/commit/716bfdc456849ba5cb94cba9ec86fbc5155f2804))

### Documentation

- Align README version references with the 0.3.0 release
  ([`496b9bb`](https://github.com/ICIJ/pystou/commit/496b9bb29bdb913cdb767e074b61b6bae147cdcb))

### Testing

- **cli**: Force stdout/stderr split in purity tests for Click <8.2 (py3.9)
  ([`d7b2ec1`](https://github.com/ICIJ/pystou/commit/d7b2ec13da1afc45218907488f0cc88084369a8f))


## v0.3.0 (2026-06-13)

### Bug Fixes

- **cli**: Route all chrome to stderr in reused core fns; restore --json purity
  ([`466234a`](https://github.com/ICIJ/pystou/commit/466234aace973bcdd19589f2bdb587f2d762adbe))

- **cli**: Route shared-module chrome to stderr; complete stdout/stderr split
  ([`d6f448c`](https://github.com/ICIJ/pystou/commit/d6f448cfd002749d493c7d812cbb70d7844344df))

- **extract**: Clean up reserved output file when decompression fails
  ([`899339f`](https://github.com/ICIJ/pystou/commit/899339f1cdb21dadd5f0e98605c14a9926689d3c))

- **extract**: Clean up reserved zst output on interrupt or failure
  ([`7232646`](https://github.com/ICIJ/pystou/commit/723264676d011aa6386bee38ef2b11f3073436aa))

- **extract**: Collapse redundant PST root directory
  ([`b6840eb`](https://github.com/ICIJ/pystou/commit/b6840eb81dc0e42a720811b7a8200ac820eb748c))

- **extract**: Do not collapse a single symlink entry
  ([`7af78e6`](https://github.com/ICIJ/pystou/commit/7af78e6bf1be4ca4f7c30ca17e69aed108d73d8d))

- **extract**: Reserve decompressed file outputs atomically (race-free)
  ([`a644cd7`](https://github.com/ICIJ/pystou/commit/a644cd7c24b88050d239b6fc87a782099ffef3f6))

- **extract**: Reserve PST output dirs atomically (race-free)
  ([`12fcd85`](https://github.com/ICIJ/pystou/commit/12fcd853b56ff2c5f6a8007ab5e9a844c36e89db))

- **extract**: Return False when PST extraction produced no output
  ([`af6383d`](https://github.com/ICIJ/pystou/commit/af6383d52ce4827cb7e33c11a6b955dae36992f5))

- **extract**: Roll back collapse on failure so output_dir survives
  ([`fa618eb`](https://github.com/ICIJ/pystou/commit/fa618eb8ee54307980f1f56cd907735a7cf3bd11))

### Build System

- Add typer + rich deps, bump to 1.0.0
  ([`a342304`](https://github.com/ICIJ/pystou/commit/a3423047061ce78d41facd6020bf27b89e39974c))

### Chores

- Gitignore .claude/worktrees/
  ([`62a2844`](https://github.com/ICIJ/pystou/commit/62a2844375fa344bf882184d6a47cb17cac8297b))

- **release**: Quarantine-by-default trash system (0.3.0)
  ([`9458fb1`](https://github.com/ICIJ/pystou/commit/9458fb1c1e1d1994d6d300fd8e4c9d9da2167881))

### Documentation

- 1.0.0 Typer+rich CLI — README usage, migration table, CHANGELOG
  ([`c609f4c`](https://github.com/ICIJ/pystou/commit/c609f4cdaa1a53080b454e46f3705316129fe2a7))

### Features

- **cleanup**: Quarantine junk by default, add --hard-delete/--trash-dir, skip trash
  ([`0439243`](https://github.com/ICIJ/pystou/commit/04392431f1875d37e1e3609d2d34360c50f44f13))

- **cleanup**: Typer command + rich output
  ([`36a17a2`](https://github.com/ICIJ/pystou/commit/36a17a27eaad5edf7058143398dc2c6d93ad37e0))

- **cli**: Add restore and trash subcommands
  ([`fe55b00`](https://github.com/ICIJ/pystou/commit/fe55b00aa6594c4e1c48ea94e07938d88ffe48e1))

- **cli**: Assemble Typer app, delete argparse/cursor/interrupt scaffolding
  ([`52fd14a`](https://github.com/ICIJ/pystou/commit/52fd14ad001d9ed4f5ea56cd822245bbd85eaedc))

- **cli**: Shared Annotated Typer option types
  ([`51f709e`](https://github.com/ICIJ/pystou/commit/51f709e9037c7d2b67d5d088ba28f0e90f52992b))

- **console**: Rich output facade (stdout data, stderr chrome, pure json)
  ([`00347b0`](https://github.com/ICIJ/pystou/commit/00347b00380433cbe6cd58fd7408c25997dbcd41))

- **dedup**: Quarantine duplicates by default, add --hard-delete/--trash-dir
  ([`c14295b`](https://github.com/ICIJ/pystou/commit/c14295ba34189d7029a6ffef1c7c23a155a97ab3))

- **dedup**: Typer command + rich tree/progress/prompt
  ([`21877e9`](https://github.com/ICIJ/pystou/commit/21877e957bfa808aee36e0f9d514371cbb749cb3))

- **doctor**: Add environment preflight command for required tools
  ([`ec3891a`](https://github.com/ICIJ/pystou/commit/ec3891ad76e6a68b425ba38cff59c75979893d9f))

- **doctor**: Typer command + rich table, typer.Exit code
  ([`0d57794`](https://github.com/ICIJ/pystou/commit/0d57794089fd16f4857ed464478224a30fe52876))

- **empty**: Typer command + rich output
  ([`e275bef`](https://github.com/ICIJ/pystou/commit/e275bef4cd0444c31dfcf53b893cba794919f89d))

- **empty,stats,identify**: Exclude .pystou-trash from directory walks
  ([`64ff5c9`](https://github.com/ICIJ/pystou/commit/64ff5c91cb797c3239272343fb1c191b823a91ef))

- **errors**: Add CrossDeviceTrashError and TrashUnavailableError
  ([`8d059c2`](https://github.com/ICIJ/pystou/commit/8d059c222d024e74e1137b1c428a490e2368a0f4))

- **extract**: Add _collapse_redundant_root helper
  ([`d505732`](https://github.com/ICIJ/pystou/commit/d505732b2d338352b0daddc4d4999412968a582c))

- **extract**: Quarantine source archives by default, add --hard-delete/--trash-dir
  ([`5206be1`](https://github.com/ICIJ/pystou/commit/5206be15631c6aa73c96faf71af9be3b3a2c3c9d))

- **extract**: Typer command + rich progress
  ([`35bf6e7`](https://github.com/ICIJ/pystou/commit/35bf6e7e61ce56f7299e69af0257c39ee6b90681))

- **fs_walker**: Add is_excluded_dir and skip .pystou-trash when scanning
  ([`2d63ffb`](https://github.com/ICIJ/pystou/commit/2d63ffb65c676df3c12c7f1c313495c4a0a6acaa))

- **identify**: Typer command + rich findings table
  ([`f1fed88`](https://github.com/ICIJ/pystou/commit/f1fed884981fd6357b9800150da7256e250acfda))

- **restore**: Typer command
  ([`1cd0117`](https://github.com/ICIJ/pystou/commit/1cd0117f835f80d34232f8fd58c9ee5ca0ea1691))

- **safe_ops**: Add atomic make_unique_dir and reserve_unique_file
  ([`b68ceaf`](https://github.com/ICIJ/pystou/commit/b68ceaf41b04bb7764e7bd75f2b982e7bb50d34c))

- **safe_ops**: Add reserve_unique_name for collision-safe renames
  ([`d819673`](https://github.com/ICIJ/pystou/commit/d819673aedeefd79c8d3a266e0c9632fc51bfe69))

- **stats**: Typer command + rich tables, pure --json
  ([`ea30843`](https://github.com/ICIJ/pystou/commit/ea3084324150bd03067cf8cdb907df78a5438348))

- **trash**: Add conflict-safe restore with optional index reconcile
  ([`5a0737d`](https://github.com/ICIJ/pystou/commit/5a0737dca3e92d4bb08532ddeab1147f54359cc4))

- **trash**: Add list_runs with tolerant ledger reader
  ([`7ddd932`](https://github.com/ICIJ/pystou/commit/7ddd932bc65584d072ff8fd3c75f0c376606d0f4))

- **trash**: Add purge with run/all/older-than selection
  ([`4745e96`](https://github.com/ICIJ/pystou/commit/4745e96d321376943738a25275b10a58eeba2bf4))

- **trash**: Add quarantine with write-ahead ledger
  ([`f298dca`](https://github.com/ICIJ/pystou/commit/f298dcade6482bd2e43015077bead1962ef1ddc4))

- **trash**: Record real invocation in ledger; test restore index reconcile
  ([`4e6fa20`](https://github.com/ICIJ/pystou/commit/4e6fa2054681c3ad8047b3e320812db248b765cd))

- **trash**: Typer list/purge sub-app, pure --json
  ([`cdbd0fd`](https://github.com/ICIJ/pystou/commit/cdbd0fdb9f032892f6135016f9d2f2d76b80ced4))

### Refactoring

- **fs_walker**: Emit scan progress via callback, drop self-print
  ([`4ac4961`](https://github.com/ICIJ/pystou/commit/4ac4961607e30f34f3cb09c2f354848ffa24cb7c))

### Testing

- **extract**: Cover best-effort collapse failure; clarify docstring
  ([`a3e8c91`](https://github.com/ICIJ/pystou/commit/a3e8c91a3f611731ecf67eca3638e4970f413fef))

- **extract**: Cover collapse rollback end-to-end through extract_pst_archive
  ([`6106303`](https://github.com/ICIJ/pystou/commit/610630399b977ac7a519bb1327f170b4ddaec730))

- **extract**: Give collapse-failure test real output for the no-output gate
  ([`e59ff1a`](https://github.com/ICIJ/pystou/commit/e59ff1a1c95a79a19e05aa141c4abfd83a851fd7))

- **trash**: Cover symlink, read-only, and cross-device quarantine paths
  ([`5d35fd4`](https://github.com/ICIJ/pystou/commit/5d35fd4a0fdceb0123fa8e9c8cfffcef838c8c68))


## v0.2.0 (2026-06-12)

### Bug Fixes

- **dedup**: Stop false 'index found' on clean start
  ([`86aee8a`](https://github.com/ICIJ/pystou/commit/86aee8a8ca438d754ef6afd7f7f1adf7593d2f77))

- **extract**: Stop false 'index found' on clean start
  ([`e40fb14`](https://github.com/ICIJ/pystou/commit/e40fb146cc262e05b81ee359e9f1cb61206afd6f))

### Chores

- Sync uv.lock to version 0.1.1
  ([`9bf5733`](https://github.com/ICIJ/pystou/commit/9bf57336fa6537aa96096c3b789fd33723247a97))

### Documentation

- Install from pypi via pip, pipx, or uv
  ([`52d05bc`](https://github.com/ICIJ/pystou/commit/52d05bc22f11662a3e83e2cf7cfa002032d4aa15))

### Features

- **indexer**: Add index_has_data helper
  ([`a01fd72`](https://github.com/ICIJ/pystou/commit/a01fd72dbf00f88d512bf27866737c15f079fd11))


## v0.1.1 (2026-06-10)

### Bug Fixes

- Trigger automated release pipeline (smoke test)
  ([`4b24fcd`](https://github.com/ICIJ/pystou/commit/4b24fcd570e4ae33bdddc7cb8924fa1dcee00e6b))

### Continuous Integration

- Publish to pypi via trusted publishing after release
  ([`ea78c81`](https://github.com/ICIJ/pystou/commit/ea78c81862b31136aef44ebb080f79c12ebb4f5e))


## v0.1.0 (2026-06-10)

### Bug Fixes

- Filter non-serializable attributes in log_configuration
  ([`6c79b99`](https://github.com/ICIJ/pystou/commit/6c79b99f3b540dadb8842f98204fc4925584b590))

- **build**: Use python3 command in Makefile
  ([`73ad286`](https://github.com/ICIJ/pystou/commit/73ad2862a29c58387b6ad3e9a035ab57899a883d))

- **common**: Correct index delete prefix matching and guard stat()
  ([`c2e2e19`](https://github.com/ICIJ/pystou/commit/c2e2e1952a5b169b6f97006901bf2a78c22e88e7))

- **common**: Make setup_logging idempotent and share log_configuration
  ([`d07bb68`](https://github.com/ICIJ/pystou/commit/d07bb68439cef92a29719bf5f6855647101ade2e))

- **common**: Safe extraction, non-clobbering outputs, zstd CLI path fix
  ([`a5da991`](https://github.com/ICIJ/pystou/commit/a5da991c20dafa4e81f4ac0a09c4e7aaf396d85d))

- **common**: Scan filesystem iteratively and isolate bad entries
  ([`a68d035`](https://github.com/ICIJ/pystou/commit/a68d035a4a958b0a899f1e00c29a9c610922d163))

- **dedup**: Preserve conflicting files on merge; validate and handle interrupts
  ([`de927fe`](https://github.com/ICIJ/pystou/commit/de927fe7039b908bf246feb30def1e1d4b12f286))

- **indexer**: Chain PystouError from sqlite errors
  ([`83f2f1c`](https://github.com/ICIJ/pystou/commit/83f2f1cb009aa79bbc3331418a2190be19dc7da8))

### Build System

- Migrate from setup.py to pyproject.toml with hatchling and uv
  ([`08cd9da`](https://github.com/ICIJ/pystou/commit/08cd9daf67ed4ff901f4c5d652a21ce3a94258b1))

- Remove python 3.6 support
  ([`8ff56a4`](https://github.com/ICIJ/pystou/commit/8ff56a4c658d996f69a253a503a60cb90d24c620))

### Chores

- Ignore local superpowers specs and plans
  ([`9f84420`](https://github.com/ICIJ/pystou/commit/9f84420d16e130e6d6153a51aba48c92dea2cc3e))

- **make**: Adopt uv-based kuroi-style Makefile
  ([`44c8714`](https://github.com/ICIJ/pystou/commit/44c8714070bcea224ecf94d5da95fac3cd3fcaac))

### Code Style

- Apply ruff import sorting, pep585 typing, and formatting
  ([`e73019b`](https://github.com/ICIJ/pystou/commit/e73019b6d6039d395f63f289dafc802cf0138635))

### Continuous Integration

- Add github action workflow
  ([`56aa26c`](https://github.com/ICIJ/pystou/commit/56aa26ca9d2bd898a4a9d226c5b99d7098c036ca))

- Add semantic-release versioning workflow on push to main
  ([`54030b1`](https://github.com/ICIJ/pystou/commit/54030b1823de0ba528f92a865e38f5108097c6c1))

- Replace workflow with lint + test matrix on python 3.9-3.12
  ([`a0b0dfd`](https://github.com/ICIJ/pystou/commit/a0b0dfd1aace295d51892b43e6655bc0b5058831))

- Test 3.12 instead of 3.8
  ([`e69e7e9`](https://github.com/ICIJ/pystou/commit/e69e7e9b16bea46e41505bed24356e3d9e50665f))

- Use string for python versions
  ([`5e0bc04`](https://github.com/ICIJ/pystou/commit/5e0bc04718514f5e6562f432a285a0360ee7189c))

### Documentation

- Add subcommand documentation for cleanup, identify, stats, and empty
  ([`7bff696`](https://github.com/ICIJ/pystou/commit/7bff696c5922bac1e69c2c17c2d8ba8ee71b1785))

- Update CLI usage for unified command
  ([`7e30ec5`](https://github.com/ICIJ/pystou/commit/7e30ec52ebf0d316c10f69985150561bf72df0b4))

Update documentation to reflect new pystou command structure with dedup and unarchive subcommands.
  Add information about split ZIP support, parallel extraction, and p7zip-full dependency.

- Update references from unarchive to extract
  ([`d02a860`](https://github.com/ICIJ/pystou/commit/d02a860b4963fed26475b42c359333c6ea86e298))

- **extract**: Document nested extraction options
  ([`878150f`](https://github.com/ICIJ/pystou/commit/878150fce28ca38b429a88ff79eb0d02e2b20814))

Add --nested and --max-depth option documentation with usage example.

### Features

- :herb:
  ([`348a0d6`](https://github.com/ICIJ/pystou/commit/348a0d666e4d7f3cbb1a0e942f14d52ec471d780))

- Add filter for specific type
  ([`3bb17ad`](https://github.com/ICIJ/pystou/commit/3bb17adc3f16c015da79049fa4aca294ff06d13c))

- Add robustness improvements across all subcommands
  ([`739ec58`](https://github.com/ICIJ/pystou/commit/739ec5822047f83f9ae7418a2f1f2cdf443ffdb3))

Filesystem safety: - Add followlinks=False to os.walk() to prevent symlink loops - Skip symlinks
  during iteration to avoid issues - Add FileNotFoundError handling for race conditions - Add
  PermissionError handling with proper error reporting

User experience: - Add keyboard interrupt (Ctrl+C) handling for graceful exit - Add progress
  reporting (every 1000 dirs or 100 files) - Add directory validation at startup

API improvements: - Change return values to tuple (removed, skipped) - Track skipped counts for
  better error reporting

Performance (stats): - Use heapq for memory-efficient largest file tracking - Add symlinks_skipped
  and errors to summary

Tests: - Update for new return value tuples - Update for renamed stats fields (largest_files)

- Add split ZIP archive support
  ([`260c7ed`](https://github.com/ICIJ/pystou/commit/260c7ed49a89fca123eb14b628ab57e2c3b18e60))

- Integrate cursor hiding in progress displays
  ([`f0eb51b`](https://github.com/ICIJ/pystou/commit/f0eb51b5e31ffabe495bb6945003738f976460fc))

- **cleanup**: Add junk file removal subcommand
  ([`4eb7772`](https://github.com/ICIJ/pystou/commit/4eb7772279fdceb3d7ca77a429371b3619a42d28))

- **cli**: Add top-level error boundary with clean exit codes
  ([`f600e95`](https://github.com/ICIJ/pystou/commit/f600e95243523e811b911721db08435a51d84446))

- **cli**: Derive --version from package __version__
  ([`34f9d66`](https://github.com/ICIJ/pystou/commit/34f9d662ec0b1c06cb7b3461b668e9e096748e9f))

- **cli**: Register empty subcommand
  ([`0f47342`](https://github.com/ICIJ/pystou/commit/0f473422e20fe75922909e4ea16e4ad0cd1b75cd))

- **common**: Add cursor utility for terminal display
  ([`cbf214f`](https://github.com/ICIJ/pystou/commit/cbf214fee96d2a231a08c31c0473cfc54af1a300))

- **common**: Add member-validated safe archive extraction
  ([`263bb77`](https://github.com/ICIJ/pystou/commit/263bb778c726d0a85bc7a590cb57e5e06eeeb1fc))

- **common**: Add scanning interrupt/cursor context manager
  ([`1e2ad3a`](https://github.com/ICIJ/pystou/commit/1e2ad3ac0d464a348c0689571596f03625a46737))

- **common**: Add shared directory validation
  ([`42691de`](https://github.com/ICIJ/pystou/commit/42691dedf646504bb9dd558c2b69bc9f836aa995))

- **common**: Add typed error hierarchy
  ([`9ba7751`](https://github.com/ICIJ/pystou/commit/9ba775177257f70fb45f64e48256951ce4951bf5))

- **common**: Add unique_path and verify_then_delete helpers
  ([`d01dae0`](https://github.com/ICIJ/pystou/commit/d01dae0fae25f952c0fb9e2de2c57f39aa3d809e))

- **empty**: Add empty directory detection and removal
  ([`aa5da47`](https://github.com/ICIJ/pystou/commit/aa5da47258dd98a63beddb494d747b82b6d34c17))

- **extract**: Add nested archive extraction
  ([`1e36617`](https://github.com/ICIJ/pystou/commit/1e36617543ed78f4f10b1fc84a532bfc7c319af1))

Add --nested and --max-depth options to recursively extract archives found inside extracted content.
  Implements process_nested_archives() function and modifies extract_and_update_index() to handle
  depth tracking.

- **extract**: Validate directory, handle interrupts, verify before delete
  ([`5c2a1ad`](https://github.com/ICIJ/pystou/commit/5c2a1adfaae26a238a122a0b1f193f38fa6a5597))

- **identify**: Add file type detection subcommand
  ([`b5104c1`](https://github.com/ICIJ/pystou/commit/b5104c182e34ce444e57f2590c111e73cf923de1))

Add identify subcommand that detects file types by magic bytes and finds files with mismatched
  extensions or encrypted ZIP archives

- **stats**: Add directory statistics subcommand
  ([`7418c69`](https://github.com/ICIJ/pystou/commit/7418c693ea8712281e1cccc1bfcff14a6ee4f7b9))

- **unarchive**: Add parallel extraction
  ([`84c0673`](https://github.com/ICIJ/pystou/commit/84c0673645999f780771ddbbabe8ff2aaaa5dd9f))

Add -p/--parallel flag to extract multiple archives concurrently using ThreadPoolExecutor. Requires
  -c flag for automatic mode.

- **unarchive**: Delete all split archive parts
  ([`2160a4a`](https://github.com/ICIJ/pystou/commit/2160a4ae7e90a929b025d4105e4b04023b7a6a04))

### Performance Improvements

- **fs_walker**: Add batched terminal updates
  ([`b724fe2`](https://github.com/ICIJ/pystou/commit/b724fe2c4c816923d8cac9c7f0fd192bb3a118f6))

Add ScanContext class to batch terminal updates every 100 entries instead of every entry, reducing
  overhead.

- **fs_walker**: Cache stat() calls
  ([`5c991a3`](https://github.com/ICIJ/pystou/commit/5c991a332a557d6a32e73a13da14939c5a12982a))

Cache stat() result per entry to avoid redundant filesystem calls.

- **fs_walker**: Optimize recursion strategy
  ([`f1055b3`](https://github.com/ICIJ/pystou/commit/f1055b3c2a1909432b57c7be756fb377ed942111))

Collect subdirs first, then recurse after DB commit for better locality and reduced memory pressure.

- **indexer**: Add database indexes
  ([`a275fed`](https://github.com/ICIJ/pystou/commit/a275fed460fa94620519d0541a2b8b94c34b8e62))

Add indexes on directories.parent_path, files.directory_path, and files.name for faster query
  performance.

- **indexer**: Cache stat() calls
  ([`67cce10`](https://github.com/ICIJ/pystou/commit/67cce10dafcda245ad8068ff17384adc80002bd2))

Cache stat() result in update_index_after_change to avoid redundant filesystem calls.

- **indexer**: Use cursor iteration
  ([`a75bb03`](https://github.com/ICIJ/pystou/commit/a75bb03e3577c1d7507aa58160169469f0142da7))

Iterate cursor directly instead of fetchall() to reduce memory usage.

- **utils**: Use cursor iteration
  ([`6a2443c`](https://github.com/ICIJ/pystou/commit/6a2443c64aebce280f4946259630e31f02412c20))

Iterate cursor directly in group_directories() to reduce memory usage.

- **utils**: Use SQL aggregates
  ([`1376b97`](https://github.com/ICIJ/pystou/commit/1376b97b9af244cec674b37734fa2ca99961c15c))

Use SUM and COUNT in get_directory_size() instead of fetching all rows.

### Refactoring

- Adopt shared validation, interrupt, and logging helpers
  ([`b36a90c`](https://github.com/ICIJ/pystou/commit/b36a90c16f3f6cc875238895bafcb9409f3a00f4))

- Finish shared log_configuration adoption; harden get_archive_files symlink walk
  ([`2344392`](https://github.com/ICIJ/pystou/commit/2344392b933bfde4d4acb77e7742113b5aa8f066))

- Lint ([`7215843`](https://github.com/ICIJ/pystou/commit/72158434cbf72e47aa6f544fe93f7a0c80817a51))

- Lint ([`9840d1e`](https://github.com/ICIJ/pystou/commit/9840d1ed35b28414a14fd94809c95674980b65c1))

- Rename unarchive module to extract
  ([`5a1323d`](https://github.com/ICIJ/pystou/commit/5a1323ddeec11e5ec2fa92209ed7bd2f34a1be3d))

- Unify CLI with subcommands
  ([`5403b74`](https://github.com/ICIJ/pystou/commit/5403b74061a95cc9304c84d5b8c555c0e12a5137))

Replace separate dedup_folders and unarchive scripts with single pystou command using subcommands.
  Extract argument parsing into reusable functions and fix logging of argparse internal attributes.

- Add pystou package with main entry point - Change parse_arguments() to add_common_arguments() -
  Add add_dedup_arguments() and add_unarchive_arguments() - Update main() functions to accept args
  parameter - Fix log_configuration() to exclude func and command keys - Update setup.py with single
  pystou entry point

- Update CLI to use extract subcommand
  ([`38abcad`](https://github.com/ICIJ/pystou/commit/38abcad43a32f6410df69e4cff512c62f735599e))

- **common**: Close index connection on init failure; add stat-guard test
  ([`fc05d6c`](https://github.com/ICIJ/pystou/commit/fc05d6ce3a9295e39e0c588b840d65c733e1bf71))

- **common**: Drop dead alias, clean partial zst output, add .gz non-clobber test
  ([`12e52b8`](https://github.com/ICIJ/pystou/commit/12e52b84176dcdd2a473b956ca5c596121d9d6b3))

- **common**: Preserve sibling scan order; tighten deep-tree assertion
  ([`3a42de1`](https://github.com/ICIJ/pystou/commit/3a42de1a34914c5ac845302e1b7f2d3436387d1b))

### Testing

- Add comprehensive tests for subcommands
  ([`b3bcddc`](https://github.com/ICIJ/pystou/commit/b3bcddc9129ff05ae3a1bafdcb5ab882a263a015))

- Rename test_unarchive to test_extract
  ([`2e6cf6d`](https://github.com/ICIJ/pystou/commit/2e6cf6d4d9d6912a806d75cd6ab52e92e520c730))

- **common**: Cover hardlink/device/nested/absolute archive members; document strict policy
  ([`3e8c172`](https://github.com/ICIJ/pystou/commit/3e8c172e1acb8a36afa6ba1fdaea38a6f4083966))

- **common**: Cover zstd CLI tar.zst extraction path
  ([`08eefb8`](https://github.com/ICIJ/pystou/commit/08eefb82f36dd38c943787de14733fba29e4b5c4))

- **cursor**: Add comprehensive cursor utility tests
  ([`d457b1c`](https://github.com/ICIJ/pystou/commit/d457b1c446bbde82750eaa80ca17d32b703341dd))

- **extract**: Update mocks for nested options
  ([`e76bf14`](https://github.com/ICIJ/pystou/commit/e76bf14ed39018464c7e53e1097068e2a1ba74e1))

Add nested and max_depth attributes to all Args mock objects to match new function signatures.
