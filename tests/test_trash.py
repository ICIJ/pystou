# tests/test_trash.py
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from common import trash
from common.errors import CrossDeviceTrashError, TrashUnavailableError


class TestQuarantineHappyPath(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _make_file(self, rel, content="x"):
        p = Path(self.root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def test_file_is_moved_into_trash_and_original_gone(self):
        victim = self._make_file("a/report.pdf", "data")
        run_id = trash.quarantine(
            [victim], self.root, operation="cleanup", command="pystou cleanup"
        )
        self.assertTrue(run_id)
        self.assertFalse(victim.exists())
        trash_root = Path(self.root) / ".pystou-trash"
        self.assertTrue((trash_root / "runs" / f"{run_id}.jsonl").is_file())

    def test_ledger_records_original_and_size(self):
        victim = self._make_file("a/report.pdf", "0123456789")
        run_id = trash.quarantine(
            [victim], self.root, operation="cleanup", command="pystou cleanup"
        )
        ledger = Path(self.root) / ".pystou-trash" / "runs" / f"{run_id}.jsonl"
        lines = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
        header, items = lines[0], lines[1:]
        self.assertTrue(header["_header"])
        self.assertEqual(header["operation"], "cleanup")
        self.assertEqual(len(items), 1)
        self.assertEqual(Path(items[0]["original"]), victim.absolute())
        self.assertEqual(items[0]["size"], 10)
        self.assertEqual(items[0]["kind"], "file")

    def test_same_basename_from_two_dirs_do_not_collide(self):
        a = self._make_file("x/dup.txt", "a")
        b = self._make_file("y/dup.txt", "bb")
        run_id = trash.quarantine([a, b], self.root, operation="cleanup", command="pystou cleanup")
        ledger = Path(self.root) / ".pystou-trash" / "runs" / f"{run_id}.jsonl"
        items = [
            json.loads(line)
            for line in ledger.read_text().splitlines()
            if line.strip() and not json.loads(line).get("_header")
        ]
        stored = [Path(self.root) / ".pystou-trash" / i["stored"] for i in items]
        self.assertEqual(len(stored), 2)
        self.assertTrue(all(p.exists() for p in stored))
        self.assertNotEqual(stored[0].parent, stored[1].parent)

    def test_directory_is_moved_with_contents(self):
        d = Path(self.root) / "olddir"
        (d / "inner").mkdir(parents=True)
        (d / "inner" / "f.txt").write_text("zz")
        run_id = trash.quarantine([d], self.root, operation="dedup", command="pystou dedup")
        self.assertFalse(d.exists())
        ledger = Path(self.root) / ".pystou-trash" / "runs" / f"{run_id}.jsonl"
        items = [
            json.loads(line)
            for line in ledger.read_text().splitlines()
            if line.strip() and not json.loads(line).get("_header")
        ]
        self.assertEqual(items[0]["kind"], "dir")
        stored = Path(self.root) / ".pystou-trash" / items[0]["stored"]
        self.assertTrue((stored / "inner" / "f.txt").is_file())

    def test_dry_run_moves_nothing(self):
        victim = self._make_file("a/report.pdf")
        run_id = trash.quarantine(
            [victim], self.root, operation="cleanup", command="pystou cleanup", dry_run=True
        )
        self.assertEqual(run_id, "")
        self.assertTrue(victim.exists())
        self.assertFalse((Path(self.root) / ".pystou-trash").exists())


class TestQuarantineEdgeCases(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_symlink_is_moved_as_link_not_dereferenced(self):
        target = Path(self.root) / "target.txt"
        target.write_text("real")
        link = Path(self.root) / "link.txt"
        link.symlink_to(target)
        run_id = trash.quarantine([link], self.root, operation="cleanup", command="pystou cleanup")
        self.assertFalse(link.is_symlink())  # link moved out
        self.assertTrue(target.is_file())  # target untouched
        ledger = Path(self.root) / ".pystou-trash" / "runs" / f"{run_id}.jsonl"
        items = [
            json.loads(x)
            for x in ledger.read_text().splitlines()
            if x.strip() and not json.loads(x).get("_header")
        ]
        self.assertTrue(items[0]["is_symlink"])
        stored = Path(self.root) / ".pystou-trash" / items[0]["stored"]
        self.assertTrue(stored.is_symlink())

    def test_read_only_root_raises_trash_unavailable(self):
        ro = Path(self.root) / "ro"
        ro.mkdir()
        victim = ro / "f.txt"
        victim.write_text("x")
        if os.geteuid() == 0:
            self.skipTest("requires non-root user")
        os.chmod(ro, 0o500)  # read+execute, no write
        try:
            with self.assertRaises(TrashUnavailableError):
                trash.quarantine([victim], ro, operation="cleanup", command="pystou cleanup")
        finally:
            os.chmod(ro, 0o700)  # restore so tearDown can clean up

    def test_cross_device_raises(self):
        victim = Path(self.root) / "f.txt"
        victim.write_text("x")
        real_lstat = os.lstat

        def fake_lstat(path, *a, **k):
            st = real_lstat(path, *a, **k)
            if str(path).endswith("f.txt"):
                return os.stat_result((*tuple(st)[:2], st.st_dev + 1, *tuple(st)[3:]))
            return st

        with (
            mock.patch("common.trash.os.lstat", side_effect=fake_lstat),
            self.assertRaises(CrossDeviceTrashError),
        ):
            trash.quarantine([victim], self.root, operation="cleanup", command="pystou cleanup")


class TestListRuns(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_lists_runs_with_counts_and_sizes(self):
        a = Path(self.root) / "a.txt"
        a.write_text("0123456789")  # 10 bytes
        trash.quarantine([a], self.root, operation="cleanup", command="pystou cleanup")
        runs = trash.list_runs(self.root)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].item_count, 1)
        self.assertEqual(runs[0].total_size, 10)
        self.assertEqual(runs[0].operation, "cleanup")

    def test_empty_when_no_trash(self):
        self.assertEqual(trash.list_runs(self.root), [])

    def test_tolerates_partial_trailing_line(self):
        a = Path(self.root) / "a.txt"
        a.write_text("x")
        run_id = trash.quarantine([a], self.root, operation="cleanup", command="pystou cleanup")
        ledger = Path(self.root) / ".pystou-trash" / "runs" / f"{run_id}.jsonl"
        with open(ledger, "a", encoding="utf-8") as f:
            f.write('{"original": "/half/written')  # truncated, no newline
        runs = trash.list_runs(self.root)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].item_count, 1)  # partial line ignored
