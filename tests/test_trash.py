# tests/test_trash.py
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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

    def test_header_records_the_trash_root(self):
        victim = self._make_file("a.txt")
        trash_dir = str(Path(self.root) / "mytrash")
        run_id = trash.quarantine(
            [victim], self.root, operation="cleanup", command="c", trash_dir=trash_dir
        )
        ledger = Path(trash_dir) / "runs" / f"{run_id}.jsonl"
        header = json.loads(ledger.read_text().splitlines()[0])
        self.assertEqual(header["trash_root"], str(Path(trash_dir).absolute()))

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

    def test_items_already_inside_the_trash_are_skipped(self):
        trash_dir = str(Path(self.root) / "mytrash")
        victim = Path(self.root) / "f.txt"
        victim.write_text("x")
        run_id = trash.quarantine(
            [victim], self.root, operation="cleanup", command="c", trash_dir=trash_dir
        )
        stored = next((Path(trash_dir) / run_id).rglob("f.txt"))
        again = trash.quarantine(
            [stored], self.root, operation="cleanup", command="c", trash_dir=trash_dir
        )
        self.assertEqual(again, "")
        self.assertTrue(stored.is_file())
        self.assertEqual(trash.restore(self.root, run_id=run_id, trash_dir=trash_dir), (1, 0))

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


class TestQuarantineCost(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_holding_dir_probes_stay_linear(self):
        items = []
        for i in range(20):
            p = Path(self.root) / f"f{i}.txt"
            p.write_text("x")
            items.append(p)
        real_mkdir = Path.mkdir
        calls = []

        def counting_mkdir(self, *args, **kwargs):
            calls.append(self)
            return real_mkdir(self, *args, **kwargs)

        with mock.patch.object(Path, "mkdir", counting_mkdir):
            run_id = trash.quarantine(items, self.root, operation="cleanup", command="c")
        run_dir = Path(self.root) / ".pystou-trash" / run_id
        probes = [c for c in calls if c.parent == run_dir]
        self.assertEqual(len(probes), len(items))


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


class TestRestore(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_round_trip_file(self):
        victim = Path(self.root) / "a" / "f.txt"
        victim.parent.mkdir(parents=True)
        victim.write_text("data")
        run_id = trash.quarantine(
            [victim], self.root, operation="cleanup", command="pystou cleanup"
        )
        restored, conflicted = trash.restore(self.root, run_id=run_id)
        self.assertEqual((restored, conflicted), (1, 0))
        self.assertTrue(victim.is_file())
        self.assertEqual(victim.read_text(), "data")

    def test_restore_all(self):
        for name in ("a.txt", "b.txt"):
            p = Path(self.root) / name
            p.write_text(name)
            trash.quarantine([p], self.root, operation="cleanup", command="c")
        restored, _conflicted = trash.restore(self.root, all_runs=True)
        self.assertEqual(restored, 2)
        self.assertTrue((Path(self.root) / "a.txt").is_file())
        self.assertTrue((Path(self.root) / "b.txt").is_file())

    def test_conflict_is_not_clobbered(self):
        victim = Path(self.root) / "f.txt"
        victim.write_text("old")
        run_id = trash.quarantine([victim], self.root, operation="cleanup", command="c")
        victim.write_text("new occupant")  # path re-occupied
        restored, conflicted = trash.restore(self.root, run_id=run_id)
        self.assertEqual((restored, conflicted), (0, 1))
        self.assertEqual(victim.read_text(), "new occupant")  # not overwritten

    def test_symlink_restored_as_link(self):
        target = Path(self.root) / "t.txt"
        target.write_text("real")
        link = Path(self.root) / "l.txt"
        link.symlink_to(target)
        run_id = trash.quarantine([link], self.root, operation="cleanup", command="c")
        trash.restore(self.root, run_id=run_id)
        self.assertTrue(link.is_symlink())

    def test_restore_by_path(self):
        a = Path(self.root) / "a.txt"
        b = Path(self.root) / "b.txt"
        a.write_text("a")
        b.write_text("b")
        trash.quarantine([a, b], self.root, operation="cleanup", command="c")
        restored, _ = trash.restore(self.root, all_runs=True, original_path=str(a))
        self.assertEqual(restored, 1)
        self.assertTrue(a.is_file())
        self.assertFalse(b.exists())  # only a restored

    def test_restore_by_path_without_run_or_all_searches_every_run(self):
        a = Path(self.root) / "a.txt"
        a.write_text("a")
        trash.quarantine([a], self.root, operation="cleanup", command="c")
        restored, _ = trash.restore(self.root, original_path=str(a))
        self.assertEqual(restored, 1)
        self.assertTrue(a.is_file())


class TestRestoreReindex(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_restore_readds_file_to_index(self):
        from common.indexer import initialize_database

        victim = Path(self.root) / "f.txt"
        victim.write_text("data")
        run_id = trash.quarantine([victim], self.root, operation="cleanup", command="c")
        conn = initialize_database(os.path.join(self.root, "index.db"))
        # index starts empty for this path; restore with conn should add it
        trash.restore(self.root, run_id=run_id, conn=conn)
        cur = conn.execute(
            "SELECT 1 FROM files WHERE directory_path = ? AND name = ?",
            (str(victim.parent.absolute()), "f.txt"),
        )
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)  # restored file is back in the index
        self.assertTrue(victim.is_file())


class TestPurge(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_purge_run_deletes_files_and_ledger(self):
        a = Path(self.root) / "a.txt"
        a.write_text("x")
        run_id = trash.quarantine([a], self.root, operation="cleanup", command="c")
        removed = trash.purge(self.root, run_id=run_id)
        self.assertEqual(removed, 1)
        self.assertEqual(trash.list_runs(self.root), [])
        self.assertFalse((Path(self.root) / ".pystou-trash" / run_id).exists())

    def test_purge_all(self):
        for name in ("a.txt", "b.txt"):
            p = Path(self.root) / name
            p.write_text("x")
            trash.quarantine([p], self.root, operation="cleanup", command="c")
        removed = trash.purge(self.root, all_runs=True)
        self.assertEqual(removed, 2)
        self.assertEqual(trash.list_runs(self.root), [])

    def test_older_than_keeps_recent(self):
        a = Path(self.root) / "a.txt"
        a.write_text("x")
        trash.quarantine([a], self.root, operation="cleanup", command="c")
        # all_runs=True so the safety gate passes and the age filter is what decides.
        removed = trash.purge(self.root, all_runs=True, older_than_days=7)
        self.assertEqual(removed, 0)  # the run is younger than 7 days
        self.assertEqual(len(trash.list_runs(self.root)), 1)

    def test_older_than_purges_old(self):
        a = Path(self.root) / "a.txt"
        a.write_text("x")
        run_id = trash.quarantine([a], self.root, operation="cleanup", command="c")
        # Backdate the ledger header's started_at to 8 days ago.
        ledger = Path(self.root) / ".pystou-trash" / "runs" / f"{run_id}.jsonl"
        lines = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
        old = datetime.now(timezone.utc) - timedelta(days=8)
        lines[0]["started_at"] = old.strftime("%Y-%m-%dT%H:%M:%SZ")
        ledger.write_text("\n".join(json.dumps(obj) for obj in lines) + "\n")
        removed = trash.purge(self.root, all_runs=True, older_than_days=7)
        self.assertEqual(removed, 1)  # the run is older than 7 days
        self.assertEqual(trash.list_runs(self.root), [])

    def test_older_than_alone_selects_old_runs(self):
        a = Path(self.root) / "a.txt"
        a.write_text("x")
        run_id = trash.quarantine([a], self.root, operation="cleanup", command="c")
        ledger = Path(self.root) / ".pystou-trash" / "runs" / f"{run_id}.jsonl"
        lines = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
        old = datetime.now(timezone.utc) - timedelta(days=8)
        lines[0]["started_at"] = old.strftime("%Y-%m-%dT%H:%M:%SZ")
        ledger.write_text("\n".join(json.dumps(obj) for obj in lines) + "\n")
        removed = trash.purge(self.root, older_than_days=7)
        self.assertEqual(removed, 1)
        self.assertEqual(trash.list_runs(self.root), [])

    def test_no_selector_purges_nothing(self):
        a = Path(self.root) / "a.txt"
        a.write_text("x")
        trash.quarantine([a], self.root, operation="cleanup", command="c")
        removed = trash.purge(self.root)
        self.assertEqual(removed, 0)
        self.assertEqual(len(trash.list_runs(self.root)), 1)


class TestHostileLedger(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _plant_ledger(self, header, items=()):
        runs_dir = Path(self.root) / ".pystou-trash" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        ledger = runs_dir / "20200101T000000Z-dead.jsonl"
        with open(ledger, "w", encoding="utf-8") as f:
            f.write(json.dumps({"_header": True, **header}) + "\n")
            for item in items:
                f.write(json.dumps(item) + "\n")
        return ledger

    def test_purge_ignores_run_id_escaping_the_trash_root(self):
        victim = Path(self.root) / "victim"
        (victim / "keep").mkdir(parents=True)
        self._plant_ledger(
            {
                "run_id": "../../victim",
                "started_at": "2020-01-01T00:00:00Z",
                "op_root": self.root,
            }
        )
        removed = trash.purge(self.root, all_runs=True)
        self.assertEqual(removed, 0)
        self.assertTrue((victim / "keep").is_dir())

    def test_restore_refuses_stored_path_outside_the_trash_root(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        loot = outside / "loot.txt"
        loot.write_text("not yours")
        self._plant_ledger(
            {"run_id": "20200101T000000Z-dead", "op_root": self.root},
            [{"original": str(Path(self.root) / "stolen.txt"), "stored": str(loot)}],
        )
        restored, conflicted = trash.restore(self.root, all_runs=True)
        self.assertEqual((restored, conflicted), (0, 1))
        self.assertTrue(loot.is_file())
        self.assertFalse((Path(self.root) / "stolen.txt").exists())

    def test_restore_refuses_original_path_outside_the_op_root(self):
        victim = Path(self.root) / "f.txt"
        victim.write_text("data")
        run_id = trash.quarantine([victim], self.root, operation="cleanup", command="c")
        ledger = Path(self.root) / ".pystou-trash" / "runs" / f"{run_id}.jsonl"
        lines = [json.loads(x) for x in ledger.read_text().splitlines() if x.strip()]
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        lines[1]["original"] = str(outside / "pwned.txt")
        ledger.write_text("\n".join(json.dumps(obj) for obj in lines) + "\n")
        restored, conflicted = trash.restore(self.root, all_runs=True)
        self.assertEqual((restored, conflicted), (0, 1))
        self.assertFalse((outside / "pwned.txt").exists())
        self.assertTrue((Path(self.root) / ".pystou-trash" / lines[1]["stored"]).is_file())


class TestDirSize(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "a").mkdir()
        (self.root / "a" / "f.bin").write_bytes(b"x" * 100)
        (self.root / "b").mkdir()
        (self.root / "b" / "g.bin").write_bytes(b"y" * 50)
        (self.root / "b" / "link").symlink_to(self.root / "a" / "f.bin")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_sums_regular_files_and_ignores_symlinks(self):
        self.assertEqual(trash._dir_size(self.root), 150)
