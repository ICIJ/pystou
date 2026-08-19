import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from normalize import manifest


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = Path(self.dir) / "run.jsonl"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_records_both_paths_losslessly(self):
        old = os.fsdecode(b"/data/Rapport \xed\xa0\xbd\xed\xb8\x80.pdf")
        new = "/data/Rapport \U0001f600.pdf"
        with manifest.ManifestWriter(self.path, {"run": "r1"}) as writer:
            writer.record("file", old, new, "repaired", ["utf8"])
        meta, entries = manifest.read(self.path)
        self.assertEqual(meta["run"], "r1")
        self.assertEqual(len(entries), 1)
        self.assertEqual(os.fsdecode(base64.b64decode(entries[0]["old_b64"])), old)
        self.assertEqual(os.fsdecode(base64.b64decode(entries[0]["new_b64"])), new)
        self.assertEqual(entries[0]["mode"], "repaired")
        self.assertEqual(entries[0]["rules"], ["utf8"])
        self.assertEqual(entries[0]["kind"], "file")

    def test_no_line_contains_a_lone_surrogate(self):
        # A lone surrogate is invalid per RFC 8259: json.dumps emits it and
        # Python reads it back, but jq and Elasticsearch can reject the line.
        old = os.fsdecode(b"/data/note_\x9f.txt")
        with manifest.ManifestWriter(self.path, {"run": "r1"}) as writer:
            writer.record("file", old, "/data/note__.txt", "stripped", ["utf8"])
        text = self.path.read_text(encoding="utf-8")
        self.assertFalse(any(0xDC80 <= ord(c) <= 0xDCFF for c in text))

    def test_every_line_parses_as_strict_json(self):
        old = os.fsdecode(b"/data/note_\x9f.txt")
        with manifest.ManifestWriter(self.path, {"run": "r1"}) as writer:
            writer.record("file", old, "/data/note__.txt", "stripped", ["utf8"])
        for line in self.path.read_text(encoding="utf-8").splitlines():
            json.loads(line)  # raises if malformed
            result = subprocess.run(["jq", "-e", "."], input=line, capture_output=True, text=True)
            if result.returncode == 127:
                self.skipTest("jq not installed")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_printable_renders_bad_bytes_readably(self):
        self.assertEqual(manifest.printable(os.fsdecode(b"a\x9f.txt")), "a\\x9f.txt")

    def test_meta_survives_a_root_with_invalid_bytes(self):
        # Normalizing a directory whose own name has bad bytes must not crash
        # while writing the meta line.
        root = os.fsdecode(b"/data/bad_\x9f")
        meta = {"run": "r1", "root": manifest.printable(root), "root_b64": manifest.encode(root)}
        with manifest.ManifestWriter(self.path, meta) as writer:
            writer.record("file", root + "/a", root + "/b", "clean", [])
        stored, _entries = manifest.read(self.path)
        self.assertEqual(stored["root"], "/data/bad_\\x9f")
        self.assertEqual(os.fsdecode(base64.b64decode(stored["root_b64"])), root)

    def test_entries_keep_insertion_order(self):
        with manifest.ManifestWriter(self.path, {"run": "r1"}) as writer:
            writer.record("file", "/a/deep/f", "/a/deep/f2", "clean", ["nfc"])
            writer.record("dir", "/a/deep", "/a/deep2", "clean", ["nfc"])
        _meta, entries = manifest.read(self.path)
        self.assertEqual([e["kind"] for e in entries], ["file", "dir"])
