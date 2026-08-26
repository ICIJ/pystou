import contextlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from common.errors import PystouError
from normalize import manifest
from normalize.main import _run, apply_rename, normalize_command, undo_run, walk_bottom_up
from normalize.rules import RULES


def make(root: Path, raw: bytes, content: bytes = b"x") -> Path:
    path = Path(os.fsdecode(os.fsencode(str(root)) + b"/" + raw))
    path.write_bytes(content)
    return path


def normalize_tree(root: Path, state: str) -> str:
    """Runs a full normalize over ``root`` and returns the run id."""
    normalize_command(
        directory=str(root),
        recursive=True,
        rule=None,
        dry_run=False,
        manifest_dir=state,
        log_dir=state,
    )
    manifests = sorted(Path(state).glob("*.jsonl"))
    assert len(manifests) == 1, f"expected one manifest, found {len(manifests)}"
    return manifests[0].stem


class TestWalkBottomUp(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_children_come_before_their_parent(self):
        (self.root / "a" / "b").mkdir(parents=True)
        (self.root / "a" / "b" / "deep.txt").write_text("x")
        (self.root / "a" / "top.txt").write_text("x")
        order = [p for p, _kind in walk_bottom_up(self.root, recursive=True)]
        self.assertLess(
            order.index(self.root / "a" / "b" / "deep.txt"), order.index(self.root / "a" / "b")
        )
        self.assertLess(order.index(self.root / "a" / "b"), order.index(self.root / "a"))

    def test_root_itself_is_never_yielded(self):
        (self.root / "f.txt").write_text("x")
        self.assertNotIn(self.root, [p for p, _kind in walk_bottom_up(self.root, recursive=True)])

    def test_trash_directory_is_skipped(self):
        junk = self.root / ".pystou-trash" / "runs"
        junk.mkdir(parents=True)
        (junk / "inside.jsonl").write_text("x")
        found = [p for p, _kind in walk_bottom_up(self.root, recursive=True)]
        self.assertEqual(found, [])

    def test_non_recursive_stops_at_the_top_level(self):
        (self.root / "sub").mkdir()
        (self.root / "sub" / "deep.txt").write_text("x")
        (self.root / "top.txt").write_text("x")
        found = [p for p, _kind in walk_bottom_up(self.root, recursive=False)]
        self.assertEqual(sorted(p.name for p in found), ["sub", "top.txt"])

    def test_symlink_is_yielded_as_a_file_and_not_followed(self):
        target = self.root / "target"
        target.mkdir()
        (target / "inside.txt").write_text("x")
        link = self.root / "link"
        link.symlink_to(target)
        kinds = dict(walk_bottom_up(self.root, recursive=True))
        self.assertEqual(kinds[link], "file")


class TestApplyRename(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_renames_a_file(self):
        old = make(self.root, b"note_\x9f.txt", b"body")
        new = apply_rename(old, "note_.txt")
        self.assertEqual(new.name, "note_.txt")
        self.assertEqual(new.read_bytes(), b"body")
        self.assertFalse(old.exists())

    def test_collision_suffixes_before_the_extension(self):
        first = make(self.root, b"note_\x9f.txt", b"1")
        second = make(self.root, b"note_\x98.txt", b"2")
        self.assertEqual(apply_rename(first, "note_.txt").name, "note_.txt")
        self.assertEqual(apply_rename(second, "note_.txt").name, "note_ (1).txt")

    def test_renames_a_directory_with_its_contents(self):
        old = Path(os.fsdecode(os.fsencode(str(self.root)) + b"/dir_\x9f"))
        old.mkdir()
        (old / "inside.txt").write_text("kept")
        new = apply_rename(old, "dir_")
        self.assertEqual((new / "inside.txt").read_text(), "kept")

    def test_does_not_clobber_an_unrelated_existing_file(self):
        (self.root / "taken.txt").write_text("original")
        old = make(self.root, b"taken\x9f.txt", b"new")
        result = apply_rename(old, "taken.txt")
        self.assertEqual(result.name, "taken (1).txt")
        self.assertEqual((self.root / "taken.txt").read_text(), "original")

    def test_renames_a_symlink_without_following_it(self):
        target = self.root / "target.txt"
        target.write_text("target body")
        link = Path(os.fsdecode(os.fsencode(str(self.root)) + b"/link_\x9f"))
        link.symlink_to(target)
        new = apply_rename(link, "link_")
        self.assertTrue(new.is_symlink())
        self.assertEqual(target.read_text(), "target body")


class TestUndo(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.state = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def _normalize(self):
        return normalize_tree(self.root, self.state)

    def test_restores_the_exact_original_bytes(self):
        bad_dir = Path(os.fsdecode(os.fsencode(str(self.root)) + b"/dir_\x9f"))
        bad_dir.mkdir()
        make(bad_dir, b"a\x9f.txt", b"body")
        before = _listing(self.root)

        run_id = self._normalize()
        self.assertNotEqual(_listing(self.root), before)

        restored, skipped = undo_run(run_id, self.state)
        self.assertEqual(skipped, 0)
        self.assertEqual(restored, 2)
        self.assertEqual(_listing(self.root), before)

    def test_skips_an_entry_whose_original_name_is_taken(self):
        make(self.root, b"note_\x9f.txt", b"body")
        run_id = self._normalize()
        # Recreate the original name so the undo target is occupied.
        make(self.root, b"note_\x9f.txt", b"squatter")
        restored, skipped = undo_run(run_id, self.state)
        self.assertEqual((restored, skipped), (0, 1))
        self.assertEqual(
            Path(os.fsdecode(os.fsencode(str(self.root)) + b"/note_\x9f.txt")).read_bytes(),
            b"squatter",
        )

    def test_dry_run_reports_without_touching_the_tree(self):
        bad_dir = Path(os.fsdecode(os.fsencode(str(self.root)) + b"/dir_\x9f"))
        bad_dir.mkdir()
        make(bad_dir, b"a\x9f.txt", b"body")

        run_id = self._normalize()
        after_normalize = _listing(self.root)

        restored, skipped = undo_run(run_id, self.state, dry_run=True)
        self.assertEqual(skipped, 0)
        self.assertEqual(restored, 2)
        self.assertEqual(_listing(self.root), after_normalize)

    def test_dry_run_resolves_two_levels_of_renamed_ancestors(self):
        dir_a = Path(os.fsdecode(os.fsencode(str(self.root)) + b"/dirA_\x9f"))
        dir_a.mkdir()
        dir_b = Path(os.fsdecode(os.fsencode(str(dir_a)) + b"/dirB_\x9f"))
        dir_b.mkdir()
        make(dir_b, b"file_\x9f.txt", b"body")

        run_id = self._normalize()
        after_normalize = _listing(self.root)

        dry_restored, dry_skipped = undo_run(run_id, self.state, dry_run=True)
        self.assertEqual(dry_skipped, 0)
        self.assertEqual(_listing(self.root), after_normalize)

        restored, skipped = undo_run(run_id, self.state)
        self.assertEqual(skipped, 0)
        self.assertEqual(dry_restored, restored)


class TestDryRunTable(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_both_columns_hold_the_full_printable_path(self):
        old = make(self.root, b"note_\x9f.txt")
        _renamed, _failed, table = _run(
            self.root, False, RULES, True, False, contextlib.nullcontext()
        )
        cells = [list(column.cells) for column in table.columns]
        self.assertEqual(cells[0], [manifest.printable(str(old))])
        self.assertEqual(cells[1], [str(self.root / "note__.txt")])


class TestManifestShape(unittest.TestCase):
    """The Elasticsearch contract: a dir entry is a prefix rewrite, recorded once."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.state = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def test_a_renamed_directory_is_recorded_once_not_per_descendant(self):
        bad_dir = Path(os.fsdecode(os.fsencode(str(self.root)) + b"/dir_\x9f"))
        bad_dir.mkdir()
        (bad_dir / "one.txt").write_text("x")
        (bad_dir / "two.txt").write_text("x")
        (bad_dir / "sub").mkdir()
        (bad_dir / "sub" / "three.txt").write_text("x")
        (bad_dir / "sub" / "nested").mkdir()

        run_id = normalize_tree(self.root, self.state)

        _meta, entries = manifest.read(manifest.manifest_path(run_id, self.state))
        self.assertEqual([e["kind"] for e in entries], ["dir"])
        self.assertEqual(entries[0]["new"], str(self.root / "dir__"))


class TestUndoSkips(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.state = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def test_skips_an_entry_whose_renamed_file_is_gone(self):
        make(self.root, b"note_\x9f.txt")
        run_id = normalize_tree(self.root, self.state)
        (self.root / "note__.txt").unlink()

        self.assertEqual(undo_run(run_id, self.state), (0, 1))

    def test_skips_an_entry_whose_rename_fails(self):
        make(self.root, b"note_\x9f.txt")
        run_id = normalize_tree(self.root, self.state)

        with mock.patch("normalize.main.os.rename", side_effect=PermissionError(13, "denied")):
            self.assertEqual(undo_run(run_id, self.state), (0, 1))

        self.assertTrue((self.root / "note__.txt").exists())

    def test_an_unknown_run_id_is_reported_not_raised_raw(self):
        with self.assertRaises(PystouError) as caught:
            undo_run("20260819T101500Z-3f2a", self.state)
        self.assertIn("20260819T101500Z-3f2a", str(caught.exception))
        self.assertIn(self.state, str(caught.exception))

    def test_a_run_id_that_escapes_the_manifest_directory_is_rejected(self):
        for run_id in ("../evil", "evil/../..", "not a run id"):
            with self.subTest(run_id=run_id), self.assertRaises(PystouError):
                undo_run(run_id, self.state)


def _listing(root: Path) -> list[bytes]:
    """Returns every path under root as raw bytes, so bad names compare exactly."""
    found = []
    for current, dirs, files in os.walk(os.fsencode(str(root))):
        for name in sorted(dirs) + sorted(files):
            found.append(os.path.join(current, name))
    return sorted(found)


class TestApplyRenameFailure(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_failed_rename_leaves_no_reserved_placeholder(self):
        # The placeholder carries the name the caller wanted, so leaving it
        # behind would push the real entry to 'name (1).ext' on the next run.
        old = make(self.root, b"note_\x9f.txt", b"body")
        with (
            mock.patch("normalize.main.os.rename", side_effect=PermissionError("denied")),
            self.assertRaises(PermissionError),
        ):
            apply_rename(old, "note_.txt")
        self.assertEqual([p.name for p in self.root.iterdir()], [old.name])

    def test_same_inode_sibling_still_gets_a_collision_suffix(self):
        # os.rename is a no-op when both paths resolve to one file, so a
        # hardlinked sibling must not be reported as renamed in place.
        old = make(self.root, b"note_\x9f.txt", b"body")
        os.link(old, self.root / "note_.txt")
        result = apply_rename(old, "note_.txt")
        self.assertEqual(result.name, "note_ (1).txt")
        self.assertFalse(os.path.lexists(old))
        self.assertEqual(result.read_bytes(), b"body")


class TestWalkBottomUpThreadCount(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        for i in range(4):
            sub = self.root / f"sub{i}"
            sub.mkdir()
            (sub / "f.txt").write_text("x")
            (sub / "deeper").mkdir()
            (sub / "deeper" / "g.txt").write_text("y")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_result_is_independent_of_worker_count(self):
        one = walk_bottom_up(self.root, True, threads=1)
        eight = walk_bottom_up(self.root, True, threads=8)
        self.assertEqual(one, eight)

    def test_every_child_precedes_its_parent(self):
        entries = walk_bottom_up(self.root, True, threads=4)
        position = {path: i for i, (path, _kind) in enumerate(entries)}
        for path, _kind in entries:
            if path.parent in position:
                self.assertLess(position[path], position[path.parent])

    def test_non_recursive_stops_at_the_top_level(self):
        entries = walk_bottom_up(self.root, False, threads=4)
        self.assertEqual(sorted(p.name for p, _kind in entries), ["sub0", "sub1", "sub2", "sub3"])
