import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from stats.main import collect_stats, process_file


class TestStatsCollectStats(unittest.TestCase):
    """Tests for statistics collection."""

    def setUp(self):
        """Set up a temporary directory with files."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        # Create test files with specific sizes
        (self.test_path / "file1.txt").write_bytes(b"x" * 100)
        (self.test_path / "file2.txt").write_bytes(b"x" * 200)
        (self.test_path / "file3.pdf").write_bytes(b"x" * 300)

        # Create a ZIP archive
        zip_path = self.test_path / "archive.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        # Create subdirectory with files
        subdir = self.test_path / "subdir"
        subdir.mkdir()
        (subdir / "file4.txt").write_bytes(b"x" * 400)

        # Create empty directory
        (self.test_path / "empty_dir").mkdir()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_collect_stats_non_recursive(self):
        """Test collecting stats without recursion."""
        stats = collect_stats(self.test_dir, recursive=False)

        # Should count files in root only
        self.assertEqual(stats["summary"]["total_files"], 4)  # 3 txt/pdf + 1 zip
        self.assertEqual(stats["summary"]["total_dirs"], 2)  # subdir + empty_dir
        self.assertEqual(stats["summary"]["archive_files"], 1)

    def test_collect_stats_recursive(self):
        """Test collecting stats with recursion."""
        stats = collect_stats(self.test_dir, recursive=True)

        # Should count all files
        self.assertEqual(stats["summary"]["total_files"], 5)  # 4 in root + 1 in subdir
        self.assertEqual(stats["summary"]["empty_dirs"], 1)

    def test_collect_stats_by_extension(self):
        """Test that extension breakdown is correct."""
        stats = collect_stats(self.test_dir, recursive=True)

        self.assertIn(".txt", stats["by_extension"])
        self.assertEqual(stats["by_extension"][".txt"]["count"], 3)  # file1, file2, file4

        self.assertIn(".pdf", stats["by_extension"])
        self.assertEqual(stats["by_extension"][".pdf"]["count"], 1)

        self.assertIn(".zip", stats["by_extension"])
        self.assertEqual(stats["by_extension"][".zip"]["count"], 1)

    def test_collect_stats_total_size(self):
        """Test that total size is calculated correctly."""
        stats = collect_stats(self.test_dir, recursive=True)

        # Sum of all file sizes (100 + 200 + 300 + zip_size + 400)
        # Note: zip size varies, so just check it's greater than the known files
        self.assertGreater(stats["summary"]["total_size"], 1000)

    def test_collect_stats_files_by_size(self):
        """Test that files are sorted by size."""
        stats = collect_stats(self.test_dir, recursive=True, top_n=10)

        # Files should be sorted by size descending
        sizes = [size for _, size in stats["largest_files"]]
        self.assertEqual(sizes, sorted(sizes, reverse=True))

    def test_collect_stats_top_zero(self):
        """--top 0 tracks no largest files instead of indexing an empty heap."""
        stats = collect_stats(self.test_dir, recursive=True, top_n=0)

        self.assertEqual(stats["largest_files"], [])
        self.assertGreater(stats["summary"]["total_files"], 0)

    def test_collect_stats_empty_directories(self):
        """Test that empty directories are detected."""
        stats = collect_stats(self.test_dir, recursive=True)

        self.assertEqual(stats["summary"]["empty_dirs"], 1)
        self.assertEqual(len(stats["empty_directories"]), 1)
        self.assertTrue(any("empty_dir" in d for d in stats["empty_directories"]))


class TestStatsProcessFile(unittest.TestCase):
    """Tests for individual file processing."""

    def setUp(self):
        """Set up a temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_process_file_updates_counts(self):
        """Test that processing a file updates statistics."""
        from collections import defaultdict

        stats = {
            "summary": {
                "total_files": 0,
                "total_size": 0,
                "archive_files": 0,
                "errors": 0,
            },
            "by_extension": defaultdict(lambda: {"count": 0, "size": 0}),
            "largest_files": [],
        }
        archive_extensions = {".zip"}

        file_path = self.test_path / "test.txt"
        file_path.write_bytes(b"x" * 100)

        process_file(file_path, stats, archive_extensions, top_n=10)

        self.assertEqual(stats["summary"]["total_files"], 1)
        self.assertEqual(stats["summary"]["total_size"], 100)
        self.assertEqual(stats["by_extension"][".txt"]["count"], 1)

    def test_process_file_detects_archive(self):
        """Test that archive files are counted."""
        from collections import defaultdict

        stats = {
            "summary": {
                "total_files": 0,
                "total_size": 0,
                "archive_files": 0,
                "errors": 0,
            },
            "by_extension": defaultdict(lambda: {"count": 0, "size": 0}),
            "largest_files": [],
        }
        archive_extensions = {".zip", ".tar"}

        zip_path = self.test_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        process_file(zip_path, stats, archive_extensions, top_n=10)

        self.assertEqual(stats["summary"]["archive_files"], 1)


class TestStatsSkipsTrash(unittest.TestCase):
    """Tests that stats never counts or reports anything under .pystou-trash."""

    def setUp(self):
        """Set up a temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_stats_ignores_trash(self):
        """Files inside .pystou-trash must not be counted; normal files are."""
        trash_file = self.test_path / ".pystou-trash" / "r" / "0" / "junk.txt"
        trash_file.parent.mkdir(parents=True)
        trash_file.write_text("junk junk junk")

        real_file = self.test_path / "real" / "data.txt"
        real_file.parent.mkdir(parents=True)
        real_file.write_text("hi")

        stats = collect_stats(self.test_dir, True)

        self.assertEqual(stats["summary"]["total_files"], 1)
        self.assertEqual(stats["summary"]["total_size"], len("hi"))
        # Nothing under .pystou-trash should appear in any reported path.
        largest_paths = [path for path, _ in stats["largest_files"]]
        self.assertTrue(any("data.txt" in p for p in largest_paths))
        self.assertFalse(any(".pystou-trash" in p for p in largest_paths))
        self.assertFalse(any(".pystou-trash" in p for p in stats["empty_directories"]))

    def test_stats_ignores_trash_non_recursive(self):
        """The non-recursive scandir branch must also skip .pystou-trash."""
        (self.test_path / ".pystou-trash").mkdir()
        real_file = self.test_path / "data.txt"
        real_file.write_text("hi")

        stats = collect_stats(self.test_dir, False)

        self.assertEqual(stats["summary"]["total_files"], 1)
        self.assertEqual(stats["summary"]["total_dirs"], 0)
        self.assertFalse(any(".pystou-trash" in p for p in stats["empty_directories"]))


class TestStatsArchiveExtensions(unittest.TestCase):
    """stats must count exactly the formats extract supports."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_counts_the_formats_extract_supports(self):
        for name in ("mail.ost", "bundle.tbz", "bundle.tzst", "notes.rar", "notes.7z"):
            (Path(self.test_dir) / name).write_bytes(b"x")

        stats = collect_stats(self.test_dir, recursive=False)

        self.assertEqual(stats["summary"]["archive_files"], 3)


if __name__ == "__main__":
    unittest.main()
