import unittest
import tempfile
import shutil
import json
import zipfile
from pathlib import Path
from unittest.mock import patch
from io import StringIO

from stats.main import (
    collect_stats,
    format_size,
    process_file,
    output_json,
    main,
)


class TestStatsFormatSize(unittest.TestCase):
    """Tests for size formatting function."""

    def test_format_bytes(self):
        """Test formatting bytes."""
        self.assertEqual(format_size(500), "500.0 B")

    def test_format_kilobytes(self):
        """Test formatting kilobytes."""
        self.assertEqual(format_size(1024), "1.0 KB")
        self.assertEqual(format_size(2048), "2.0 KB")

    def test_format_megabytes(self):
        """Test formatting megabytes."""
        self.assertEqual(format_size(1024 * 1024), "1.0 MB")

    def test_format_gigabytes(self):
        """Test formatting gigabytes."""
        self.assertEqual(format_size(1024 * 1024 * 1024), "1.0 GB")

    def test_format_terabytes(self):
        """Test formatting terabytes."""
        self.assertEqual(format_size(1024 * 1024 * 1024 * 1024), "1.0 TB")


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
        stats = collect_stats(self.test_dir, recursive=True)

        # Files should be sorted by size descending
        sizes = [size for _, size in stats["files_by_size"]]
        self.assertEqual(sizes, sorted(sizes, reverse=True))

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
            },
            "by_extension": defaultdict(lambda: {"count": 0, "size": 0}),
            "files_by_size": [],
        }
        archive_extensions = {".zip"}

        file_path = self.test_path / "test.txt"
        file_path.write_bytes(b"x" * 100)

        process_file(file_path, stats, archive_extensions)

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
            },
            "by_extension": defaultdict(lambda: {"count": 0, "size": 0}),
            "files_by_size": [],
        }
        archive_extensions = {".zip", ".tar"}

        zip_path = self.test_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        process_file(zip_path, stats, archive_extensions)

        self.assertEqual(stats["summary"]["archive_files"], 1)


class TestStatsOutputJson(unittest.TestCase):
    """Tests for JSON output."""

    def test_output_json_format(self):
        """Test that JSON output is valid."""
        from collections import defaultdict

        stats = {
            "summary": {
                "total_files": 10,
                "total_dirs": 5,
                "total_size": 1000,
                "empty_dirs": 1,
                "archive_files": 2,
            },
            "by_extension": defaultdict(lambda: {"count": 0, "size": 0}),
            "files_by_size": [("/path/file1.txt", 500), ("/path/file2.txt", 300)],
            "empty_directories": ["/path/empty"],
        }
        stats["by_extension"][".txt"] = {"count": 5, "size": 800}

        with patch("sys.stdout", new=StringIO()) as mock_stdout:
            output_json(stats, top_n=10)
            output = mock_stdout.getvalue()

        # Should be valid JSON
        parsed = json.loads(output)
        self.assertEqual(parsed["summary"]["total_files"], 10)
        self.assertIn("by_extension", parsed)
        self.assertIn("largest_files", parsed)


class TestStatsMain(unittest.TestCase):
    """Tests for the main stats function."""

    def setUp(self):
        """Set up a temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        # Create some test files
        (self.test_path / "file1.txt").write_bytes(b"x" * 100)
        (self.test_path / "file2.pdf").write_bytes(b"x" * 200)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    @patch("builtins.print")
    def test_main_text_output(self, mock_print):
        """Test main with text output."""
        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "top": 10,
                "by_extension": True,
                "by_size": False,
                "json": False,
            },
        )
        main(args)

        # Should print statistics header
        calls = [str(call) for call in mock_print.call_args_list]
        found_header = any("Statistics" in call for call in calls)
        self.assertTrue(found_header)

    @patch("builtins.print")
    def test_main_json_output(self, mock_print):
        """Test main with JSON output."""
        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "top": 10,
                "by_extension": False,
                "by_size": False,
                "json": True,
            },
        )
        main(args)

        # Should print valid JSON
        calls = mock_print.call_args_list
        # Find the JSON output call
        json_output = None
        for call in calls:
            try:
                json_output = json.loads(str(call[0][0]))
                break
            except (json.JSONDecodeError, IndexError):
                continue

        self.assertIsNotNone(json_output)
        self.assertIn("summary", json_output)

    @patch("builtins.print")
    def test_main_by_size(self, mock_print):
        """Test main with --by-size flag."""
        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "top": 10,
                "by_extension": False,
                "by_size": True,
                "json": False,
            },
        )
        main(args)

        # Should print largest files section
        calls = [str(call) for call in mock_print.call_args_list]
        found_size_section = any("Largest" in call for call in calls)
        self.assertTrue(found_size_section)


if __name__ == "__main__":
    unittest.main()
