import io
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import typer
from typer.testing import CliRunner

from common import console
from identify.main import identify_command


def _app():
    app = typer.Typer()
    app.command()(identify_command)
    return app


def _make_encrypted_zip(path: Path) -> None:
    """Create a ZIP file with the encrypted flag set on one entry.

    Python's zipfile module cannot write encrypted archives natively, so we
    build the bytes by hand: write a normal ZIP then flip flag_bits bit-0 in
    the local file header and the central directory entry.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("secret.txt", "hidden")
    data = bytearray(buf.getvalue())

    # Local file header signature: PK\x03\x04; general purpose flag at offset 6.
    sig = b"\x50\x4b\x03\x04"
    idx = data.find(sig)
    if idx != -1:
        data[idx + 6] |= 0x01  # set encrypted flag

    # Central directory entry: PK\x01\x02; general purpose flag at offset 8.
    cd_sig = b"\x50\x4b\x01\x02"
    cd_idx = data.find(cd_sig)
    if cd_idx != -1:
        data[cd_idx + 8] |= 0x01  # set encrypted flag

    path.write_bytes(bytes(data))


class TestIdentifyCommand(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.runner = CliRunner()
        # Redirect console output so assertions can inspect it.
        self.out = io.StringIO()
        self.err = io.StringIO()
        console.configure(no_color=True, quiet=False, out_file=self.out, err_file=self.err)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        # Restore console to defaults so other tests are not affected.
        console.configure()

    def _args(self, *extra):
        return [self.dir, "--log-dir", self.dir, "--db-dir", self.dir, *extra]

    def _invoke(self, *extra):
        return self.runner.invoke(_app(), self._args(*extra))

    # ------------------------------------------------------------------
    # test_check_mismatch_finds_issue
    # Trigger: a ZIP file given a .jpg extension — magic bytes are PK\x03\x04
    # (detected as "zip") but the extension maps to expected type "jpeg".
    # check_extension_mismatches raises this as an extension mismatch.
    # ------------------------------------------------------------------
    def test_check_mismatch_finds_issue(self):
        fake_jpg = Path(self.dir) / "fake.jpg"
        with zipfile.ZipFile(fake_jpg, "w") as zf:
            zf.writestr("test.txt", "content")

        r = self._invoke("-r", "--check", "mismatch")
        self.assertEqual(r.exit_code, 0, r.output)
        # The table is written to self.out via print_table.
        self.assertIn("fake.jpg", self.out.getvalue())

    # ------------------------------------------------------------------
    # test_check_all_runs
    # Runs both mismatch and encrypted checks; should exit 0 with no crash.
    # ------------------------------------------------------------------
    def test_check_all_runs(self):
        zip_path = Path(self.dir) / "clean.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("doc.txt", "hello")

        r = self._invoke("--check", "all")
        self.assertEqual(r.exit_code, 0, r.output)

    # ------------------------------------------------------------------
    # test_no_issues_clean_dir
    # An empty directory should produce "No issues found." on stderr via
    # console.status().
    # ------------------------------------------------------------------
    def test_no_issues_clean_dir(self):
        r = self._invoke()
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("No issues found.", self.err.getvalue())

    # ------------------------------------------------------------------
    # test_extensions_filter
    # Passing --extensions .zip limits the scan to .zip files; command must
    # exit 0 and not crash.
    # ------------------------------------------------------------------
    def test_extensions_filter(self):
        zip_path = Path(self.dir) / "archive.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("a.txt", "data")

        r = self._invoke("--extensions", ".zip")
        self.assertEqual(r.exit_code, 0, r.output)

    # ------------------------------------------------------------------
    # test_check_encrypted_finds_issue
    # Trigger: a ZIP file whose local-file-header and central-directory
    # general-purpose flag has bit-0 set (the "encrypted" flag per the ZIP
    # spec).  check_encrypted_archives detects this via (info.flag_bits & 0x1).
    # ------------------------------------------------------------------
    def test_check_encrypted_finds_issue(self):
        enc_zip = Path(self.dir) / "encrypted.zip"
        _make_encrypted_zip(enc_zip)

        r = self._invoke("--check", "encrypted")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("encrypted.zip", self.out.getvalue())

    # ------------------------------------------------------------------
    # test_default_runs_all_checks
    # When no --check flag is given the command must default to running all
    # checks (equivalent to --check all).  A clean dir → "No issues found."
    # ------------------------------------------------------------------
    def test_default_runs_all_checks(self):
        r = self._invoke()
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("No issues found.", self.err.getvalue())


if __name__ == "__main__":
    unittest.main()
