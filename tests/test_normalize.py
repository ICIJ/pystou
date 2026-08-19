import os
import shutil
import tempfile
import unittest
from pathlib import Path

from normalize.main import apply_rename, walk_bottom_up


def make(root: Path, raw: bytes, content: bytes = b"x") -> Path:
    path = Path(os.fsdecode(os.fsencode(str(root)) + b"/" + raw))
    path.write_bytes(content)
    return path


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
