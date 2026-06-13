import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

from common import trash
from common.indexer import close_database, initialize_database
from common.utils import get_archive_files
from extract.main import delete_archive_file, manage_index, process_archive


class TestExtract(unittest.TestCase):
    def setUp(self):
        """
        Set up a temporary directory and initialize the database.
        Create a ZIP archive containing a test file without placing the test file in the directory initially.
        """
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        # Initialize database
        self.db_path = os.path.join(self.test_dir, "filesystem_index.db")
        self.conn = initialize_database(self.test_dir)
        # Set up test archives
        self.setup_test_archives()

    def tearDown(self):
        """
        Tear down the temporary directory and close the database connection.
        """
        # Close database connection
        close_database(self.conn)
        # Remove temporary directory
        shutil.rmtree(self.test_dir)

    def setup_test_archives(self):
        """
        Create a ZIP archive containing a test file without placing the test file in the test directory.
        """
        # Create a separate temporary directory to hold files to be archived
        with tempfile.TemporaryDirectory() as archive_source_dir:
            archive_source_path = Path(archive_source_dir)
            # Create a test file to archive
            test_file = archive_source_path / "test_file.txt"
            test_file.touch()
            # Create a ZIP archive in test_dir
            import zipfile

            zip_path = Path(self.test_dir) / "archive.zip"
            with zipfile.ZipFile(zip_path, "w") as zipf:
                zipf.write(test_file, arcname="test_file.txt")
            # Note: test_file.txt is not present in test_dir initially

    @patch("builtins.print")
    @patch("builtins.input", return_value="1")  # Mock user input to '1' (extract)
    def test_process_archive_extract(self, mock_input, mock_print):
        """
        Test extracting an archive.
        Simulates user choosing to extract and keep the archive.
        """
        args = type(
            "Args",
            (),
            {
                "dry_run": False,
                "default_choice": None,
                "default_delete_choice": None,
                "nested": False,
                "max_depth": 10,
                "directory": self.test_dir,
                "hard_delete": False,
                "trash_dir": None,
            },
        )
        archive_files = get_archive_files(self.test_dir, recursive=False)
        self.assertEqual(len(archive_files), 1)
        for archive_file in archive_files:
            process_archive(archive_file, args, self.conn)
        # Check that the file was extracted
        self.assertTrue((Path(self.test_dir) / "test_file.txt").exists())
        # Check that the archive still exists since delete_choice is None (no prompt simulated)

    @patch("builtins.print")
    @patch(
        "builtins.input", side_effect=["1", "1"]
    )  # Mock user input to '1' (extract) and '1' (delete)
    def test_process_archive_extract_and_delete(self, mock_input, mock_print):
        """
        Test extracting an archive and then deleting the archive file.
        """
        args = type(
            "Args",
            (),
            {
                "dry_run": False,
                "default_choice": None,
                "default_delete_choice": None,
                "nested": False,
                "max_depth": 10,
                "directory": self.test_dir,
                "hard_delete": False,
                "trash_dir": None,
            },
        )
        archive_files = get_archive_files(self.test_dir, recursive=False)
        self.assertEqual(len(archive_files), 1)
        for archive_file in archive_files:
            process_archive(archive_file, args, self.conn)
        # Check that the file was extracted and the archive was quarantined (default)
        self.assertTrue((Path(self.test_dir) / "test_file.txt").exists())
        self.assertFalse((Path(self.test_dir) / "archive.zip").exists())
        self.assertEqual(len(trash.list_runs(self.test_dir)), 1)

    @patch("builtins.print")
    @patch("builtins.input", return_value="2")  # Mock user input to '2' (skip)
    def test_process_archive_skip(self, mock_input, mock_print):
        """
        Test skipping the extraction of an archive.
        """
        args = type(
            "Args",
            (),
            {
                "dry_run": False,
                "default_choice": None,
                "default_delete_choice": None,
                "nested": False,
                "max_depth": 10,
                "directory": self.test_dir,
                "hard_delete": False,
                "trash_dir": None,
            },
        )
        archive_files = get_archive_files(self.test_dir, recursive=False)
        self.assertEqual(len(archive_files), 1)
        for archive_file in archive_files:
            process_archive(archive_file, args, self.conn)
        # Check that the file was not extracted
        self.assertFalse((Path(self.test_dir) / "test_file.txt").exists())
        # Archive should still exist
        self.assertTrue((Path(self.test_dir) / "archive.zip").exists())

    @patch("builtins.print")
    @patch("builtins.input", return_value="1")  # Mock user input to '1' (extract) and '2' (keep)
    def test_process_archive_extract_keep_archive(self, mock_input, mock_print):
        """
        Test extracting an archive and choosing to keep the archive file.
        """
        args = type(
            "Args",
            (),
            {
                "dry_run": False,
                "default_choice": None,
                "default_delete_choice": None,
                "nested": False,
                "max_depth": 10,
                "directory": self.test_dir,
                "hard_delete": False,
                "trash_dir": None,
            },
        )
        with patch("builtins.input", side_effect=["1", "2"]):
            archive_files = get_archive_files(self.test_dir, recursive=False)
            self.assertEqual(len(archive_files), 1)
            for archive_file in archive_files:
                process_archive(archive_file, args, self.conn)
        # Check that the file was extracted and archive was kept
        self.assertTrue((Path(self.test_dir) / "test_file.txt").exists())
        self.assertTrue((Path(self.test_dir) / "archive.zip").exists())

    @patch("builtins.print")
    @patch("builtins.input", return_value="1")  # Mock user input for dry run
    def test_process_archive_dry_run_extract_and_delete(self, mock_input, mock_print):
        """
        Test performing a dry run extraction and deletion.
        """
        args = type(
            "Args",
            (),
            {
                "dry_run": True,
                "default_choice": None,
                "default_delete_choice": None,
                "nested": False,
                "max_depth": 10,
                "directory": self.test_dir,
                "hard_delete": False,
                "trash_dir": None,
            },
        )
        with patch("builtins.input", side_effect=["1", "1"]):
            archive_files = get_archive_files(self.test_dir, recursive=False)
            self.assertEqual(len(archive_files), 1)
            for archive_file in archive_files:
                process_archive(archive_file, args, self.conn)
        # Check that the file was not actually extracted
        self.assertFalse((Path(self.test_dir) / "test_file.txt").exists())
        # Check that the archive still exists
        self.assertTrue((Path(self.test_dir) / "archive.zip").exists())

    @patch("builtins.print")
    @patch("builtins.input", return_value="1")  # Mock user input for default choices
    def test_process_archive_default_choices(self, mock_input, mock_print):
        """
        Test processing archives with default choices set for extraction and deletion.
        """
        args = type(
            "Args",
            (),
            {
                "dry_run": False,
                "default_choice": 1,  # Extract
                "default_delete_choice": 1,  # Delete after extraction
                "nested": False,
                "max_depth": 10,
                "directory": self.test_dir,
                "hard_delete": False,
                "trash_dir": None,
            },
        )
        with patch("builtins.input", return_value="1"):
            archive_files = get_archive_files(self.test_dir, recursive=False)
            self.assertEqual(len(archive_files), 1)
            for archive_file in archive_files:
                process_archive(archive_file, args, self.conn)
        # Check that the file was extracted and the archive was quarantined (default)
        self.assertTrue((Path(self.test_dir) / "test_file.txt").exists())
        self.assertFalse((Path(self.test_dir) / "archive.zip").exists())
        self.assertEqual(len(trash.list_runs(self.test_dir)), 1)

    @patch("builtins.print")
    @patch("builtins.input", return_value="2")  # Mock user input for default delete choice
    def test_process_archive_default_delete_choice_keep(self, mock_input, mock_print):
        """
        Test processing archives with default choices set for extraction and keeping the archive.
        """
        args = type(
            "Args",
            (),
            {
                "dry_run": False,
                "default_choice": 1,  # Extract
                "default_delete_choice": 2,  # Keep after extraction
                "nested": False,
                "max_depth": 10,
                "directory": self.test_dir,
                "hard_delete": False,
                "trash_dir": None,
            },
        )
        with patch("builtins.input", return_value="2"):
            archive_files = get_archive_files(self.test_dir, recursive=False)
            self.assertEqual(len(archive_files), 1)
            for archive_file in archive_files:
                process_archive(archive_file, args, self.conn)
        # Check that the file was extracted and archive was kept
        self.assertTrue((Path(self.test_dir) / "test_file.txt").exists())
        self.assertTrue((Path(self.test_dir) / "archive.zip").exists())

    @patch("builtins.print")
    @patch(
        "builtins.input", side_effect=["1", "1"]
    )  # Mock user input to '1' (extract) and '1' (delete)
    def test_process_archive_extract_only(self, mock_input, mock_print):
        """
        Test extracting an archive without any default choices.
        """
        args = type(
            "Args",
            (),
            {
                "dry_run": False,
                "default_choice": None,
                "default_delete_choice": None,
                "nested": False,
                "max_depth": 10,
                "directory": self.test_dir,
                "hard_delete": False,
                "trash_dir": None,
            },
        )
        archive_files = get_archive_files(self.test_dir, recursive=False)
        self.assertEqual(len(archive_files), 1)
        for archive_file in archive_files:
            process_archive(archive_file, args, self.conn)
        # Check that the file was extracted and the archive was quarantined (default)
        self.assertTrue((Path(self.test_dir) / "test_file.txt").exists())
        self.assertFalse((Path(self.test_dir) / "archive.zip").exists())
        self.assertEqual(len(trash.list_runs(self.test_dir)), 1)

    @patch("builtins.print")
    @patch("builtins.input", return_value="2")  # Mock user input to '2' (skip)
    def test_process_archive_skip_only(self, mock_input, mock_print):
        """
        Test skipping the extraction of an archive without any default choices.
        """
        args = type(
            "Args",
            (),
            {
                "dry_run": False,
                "default_choice": None,
                "default_delete_choice": None,
                "nested": False,
                "max_depth": 10,
                "directory": self.test_dir,
                "hard_delete": False,
                "trash_dir": None,
            },
        )
        archive_files = get_archive_files(self.test_dir, recursive=False)
        self.assertEqual(len(archive_files), 1)
        for archive_file in archive_files:
            process_archive(archive_file, args, self.conn)
        # Check that the file was not extracted
        self.assertFalse((Path(self.test_dir) / "test_file.txt").exists())
        # Archive should still exist
        self.assertTrue((Path(self.test_dir) / "archive.zip").exists())

    @patch("builtins.print")
    def test_parallel_keeps_archive_when_extraction_fails(self, mock_print):
        """A failed extraction must not delete the source archive in parallel mode."""
        from pathlib import Path as _P

        from extract.main import process_archives_parallel

        bad = _P(self.test_dir) / "broken.zip"
        bad.write_bytes(b"not a real zip")
        args = type(
            "Args",
            (),
            {
                "dry_run": False,
                "default_choice": 1,
                "default_delete_choice": 1,
                "parallel": 2,
                "nested": False,
                "max_depth": 10,
                "directory": self.test_dir,
                "hard_delete": False,
                "trash_dir": None,
            },
        )
        process_archives_parallel([bad], args, self.conn)
        self.assertTrue(bad.exists())  # kept because extraction failed


class TestExtractManageIndex(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.conn = initialize_database(self.test_dir)
        self.args = SimpleNamespace(directory=self.test_dir, recursive=True)

    def tearDown(self):
        close_database(self.conn)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _populate(self):
        self.conn.execute(
            "INSERT INTO directories (path, parent_path, mtime) VALUES ('/a', '/', 0)"
        )
        self.conn.commit()

    @mock.patch("extract.main.collect_directories")
    @mock.patch("extract.main.prompt_use_existing_index")
    def test_no_file_scans_without_prompt(self, prompt, collect):
        manage_index(self.conn, self.args, index_existed=False)
        prompt.assert_not_called()
        collect.assert_called_once()

    @mock.patch("extract.main.collect_directories")
    @mock.patch("extract.main.prompt_use_existing_index")
    def test_empty_file_scans_without_prompt(self, prompt, collect):
        manage_index(self.conn, self.args, index_existed=True)
        prompt.assert_not_called()
        collect.assert_called_once()

    @mock.patch("extract.main.collect_directories")
    @mock.patch("extract.main.prompt_use_existing_index", return_value=True)
    def test_populated_file_reused_skips_scan(self, prompt, collect):
        self._populate()
        manage_index(self.conn, self.args, index_existed=True)
        prompt.assert_called_once()
        collect.assert_not_called()

    @mock.patch("extract.main.collect_directories")
    @mock.patch("extract.main.prompt_use_existing_index", return_value=False)
    def test_populated_file_rescan_calls_collect(self, prompt, collect):
        self._populate()
        manage_index(self.conn, self.args, index_existed=True)
        prompt.assert_called_once()
        collect.assert_called_once()


class TestExtractQuarantine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_delete_archive_quarantines_by_default(self):
        arc = Path(self.test_dir) / "a.zip"
        arc.write_text("PK")
        conn = initialize_database(self.test_dir)
        delete_archive_file(arc, conn, dry_run=False, op_root=self.test_dir, hard_delete=False)
        conn.close()
        self.assertFalse(arc.exists())
        self.assertEqual(len(trash.list_runs(self.test_dir)), 1)

    def test_delete_archive_hard_delete(self):
        arc = Path(self.test_dir) / "a.zip"
        arc.write_text("PK")
        conn = initialize_database(self.test_dir)
        delete_archive_file(arc, conn, dry_run=False, op_root=self.test_dir, hard_delete=True)
        conn.close()
        self.assertFalse(arc.exists())
        self.assertEqual(trash.list_runs(self.test_dir), [])


if __name__ == "__main__":
    unittest.main()
