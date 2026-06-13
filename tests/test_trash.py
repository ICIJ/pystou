# tests/test_trash.py
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from common import trash


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
