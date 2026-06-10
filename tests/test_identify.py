import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from identify.main import (
    check_encrypted_archives,
    check_extension_mismatches,
    collect_files,
    detect_file_type,
    main,
)


class TestIdentifyDetectFileType(unittest.TestCase):
    """Tests for file type detection by magic bytes."""

    def setUp(self):
        """Set up a temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_detect_zip_file(self):
        """Test detecting a ZIP file."""
        zip_path = self.test_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        file_type = detect_file_type(zip_path)
        self.assertEqual(file_type, "zip")

    def test_detect_gzip_file(self):
        """Test detecting a GZIP file."""
        import gzip

        gz_path = self.test_path / "test.gz"
        with gzip.open(gz_path, "wb") as f:
            f.write(b"content")

        file_type = detect_file_type(gz_path)
        self.assertEqual(file_type, "gzip")

    def test_detect_png_file(self):
        """Test detecting a PNG file by magic bytes."""
        png_path = self.test_path / "test.png"
        # PNG magic bytes
        png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        file_type = detect_file_type(png_path)
        self.assertEqual(file_type, "png")

    def test_detect_jpeg_file(self):
        """Test detecting a JPEG file by magic bytes."""
        jpg_path = self.test_path / "test.jpg"
        # JPEG magic bytes
        jpg_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        file_type = detect_file_type(jpg_path)
        self.assertEqual(file_type, "jpeg")

    def test_detect_pdf_file(self):
        """Test detecting a PDF file by magic bytes."""
        pdf_path = self.test_path / "test.pdf"
        # PDF magic bytes
        pdf_path.write_bytes(b"%PDF-1.4" + b"\x00" * 100)

        file_type = detect_file_type(pdf_path)
        self.assertEqual(file_type, "pdf")

    def test_detect_unknown_file(self):
        """Test detecting an unknown file type."""
        unknown_path = self.test_path / "test.unknown"
        unknown_path.write_bytes(b"random content here")

        file_type = detect_file_type(unknown_path)
        self.assertIsNone(file_type)

    def test_detect_empty_file(self):
        """Test handling of empty files."""
        empty_path = self.test_path / "empty.txt"
        empty_path.touch()

        file_type = detect_file_type(empty_path)
        self.assertIsNone(file_type)


class TestIdentifyExtensionMismatch(unittest.TestCase):
    """Tests for extension mismatch detection."""

    def setUp(self):
        """Set up a temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_no_mismatch_correct_extension(self):
        """Test that correctly named files don't trigger mismatch."""
        zip_path = self.test_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        issues = check_extension_mismatches([zip_path])
        self.assertEqual(len(issues), 0)

    def test_mismatch_zip_as_jpg(self):
        """Test detecting a ZIP file disguised as JPG."""
        fake_jpg = self.test_path / "fake.jpg"
        with zipfile.ZipFile(fake_jpg, "w") as zf:
            zf.writestr("test.txt", "content")

        issues = check_extension_mismatches([fake_jpg])
        self.assertEqual(len(issues), 1)
        self.assertIn("mismatch", issues[0][1].lower())

    def test_mismatch_png_as_jpg(self):
        """Test detecting a PNG file disguised as JPG."""
        fake_jpg = self.test_path / "fake.jpg"
        fake_jpg.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        issues = check_extension_mismatches([fake_jpg])
        self.assertEqual(len(issues), 1)

    def test_unknown_extension_no_mismatch(self):
        """Test that unknown extensions don't trigger false positives."""
        unknown = self.test_path / "file.xyz"
        unknown.write_bytes(b"random content")

        issues = check_extension_mismatches([unknown])
        self.assertEqual(len(issues), 0)


class TestIdentifyEncryptedArchives(unittest.TestCase):
    """Tests for encrypted archive detection."""

    def setUp(self):
        """Set up a temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_unencrypted_zip(self):
        """Test that unencrypted ZIPs are not flagged."""
        zip_path = self.test_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        issues = check_encrypted_archives([zip_path])
        self.assertEqual(len(issues), 0)

    def test_non_zip_file_ignored(self):
        """Test that non-ZIP files are ignored."""
        txt_path = self.test_path / "test.txt"
        txt_path.write_text("content")

        issues = check_encrypted_archives([txt_path])
        self.assertEqual(len(issues), 0)

    def test_invalid_zip_ignored(self):
        """Test that invalid ZIP files are handled gracefully."""
        fake_zip = self.test_path / "fake.zip"
        fake_zip.write_bytes(b"not a zip file")

        issues = check_encrypted_archives([fake_zip])
        self.assertEqual(len(issues), 0)


class TestIdentifyCollectFiles(unittest.TestCase):
    """Tests for file collection."""

    def setUp(self):
        """Set up a temporary directory with files."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        # Create test files
        (self.test_path / "file1.zip").touch()
        (self.test_path / "file2.pdf").touch()
        (self.test_path / "file3.txt").touch()

        # Create subdirectory with files
        subdir = self.test_path / "subdir"
        subdir.mkdir()
        (subdir / "file4.zip").touch()
        (subdir / "file5.jpg").touch()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_collect_files_non_recursive(self):
        """Test collecting files without recursion."""
        files = collect_files(self.test_dir, recursive=False, extensions_filter=None)

        self.assertEqual(len(files), 3)
        file_names = {f.name for f in files}
        self.assertIn("file1.zip", file_names)
        self.assertNotIn("file4.zip", file_names)

    def test_collect_files_recursive(self):
        """Test collecting files with recursion."""
        files = collect_files(self.test_dir, recursive=True, extensions_filter=None)

        self.assertEqual(len(files), 5)

    def test_collect_files_with_extension_filter(self):
        """Test collecting files with extension filter."""
        files = collect_files(self.test_dir, recursive=True, extensions_filter={".zip"})

        self.assertEqual(len(files), 2)
        for f in files:
            self.assertEqual(f.suffix.lower(), ".zip")

    def test_collect_files_multiple_extensions(self):
        """Test collecting files with multiple extensions filter."""
        files = collect_files(self.test_dir, recursive=True, extensions_filter={".zip", ".pdf"})

        self.assertEqual(len(files), 3)


class TestIdentifyMain(unittest.TestCase):
    """Tests for the main identify function."""

    def setUp(self):
        """Set up a temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir)

    @patch("builtins.print")
    def test_main_no_files(self, mock_print):
        """Test main when no files are found."""
        # Create a separate directory for scanning (log file goes to test_dir)
        scan_dir = self.test_path / "scan"
        scan_dir.mkdir()

        args = type(
            "Args",
            (),
            {
                "directory": str(scan_dir),
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "check_mismatch": True,
                "check_encrypted": False,
                "check_all": False,
                "extensions": None,
            },
        )
        main(args)

        # Should print a message about 0 files
        calls = [str(call) for call in mock_print.call_args_list]
        found_zero_files = any("0 files" in call or "No files" in call for call in calls)
        self.assertTrue(found_zero_files, f"Expected '0 files' message, got: {calls}")

    @patch("builtins.print")
    def test_main_no_issues(self, mock_print):
        """Test main when no issues are found."""
        # Create a correctly named ZIP
        zip_path = self.test_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "check_mismatch": True,
                "check_encrypted": False,
                "check_all": False,
                "extensions": None,
            },
        )
        main(args)

        mock_print.assert_any_call("No issues found.")

    @patch("builtins.print")
    def test_main_finds_mismatch(self, mock_print):
        """Test main finds extension mismatches."""
        # Create a ZIP disguised as JPG
        fake_jpg = self.test_path / "fake.jpg"
        with zipfile.ZipFile(fake_jpg, "w") as zf:
            zf.writestr("test.txt", "content")

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "check_mismatch": True,
                "check_encrypted": False,
                "check_all": False,
                "extensions": None,
            },
        )
        main(args)

        # Check that issues were found
        calls = [str(call) for call in mock_print.call_args_list]
        found_issue = any("issue" in call.lower() or "mismatch" in call.lower() for call in calls)
        self.assertTrue(found_issue)

    @patch("builtins.print")
    def test_main_check_all(self, mock_print):
        """Test main with --check-all flag."""
        zip_path = self.test_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "content")

        args = type(
            "Args",
            (),
            {
                "directory": self.test_dir,
                "recursive": False,
                "dry_run": False,
                "log_dir": self.test_dir,
                "check_mismatch": False,
                "check_encrypted": False,
                "check_all": True,
                "extensions": None,
            },
        )
        main(args)

        # Should enable both checks
        self.assertTrue(args.check_mismatch)
        self.assertTrue(args.check_encrypted)


if __name__ == "__main__":
    unittest.main()
