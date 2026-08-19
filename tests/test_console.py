import io
import json
import unittest

from common import console


class TestConsole(unittest.TestCase):
    def setUp(self):
        console.configure(no_color=True, quiet=False)

    def test_print_json_is_pure(self):
        buf = io.StringIO()
        console.print_json({"a": 1, "b": [2, 3]}, file=buf)
        self.assertEqual(json.loads(buf.getvalue()), {"a": 1, "b": [2, 3]})
        self.assertNotIn("\x1b[", buf.getvalue())

    def test_human_size_scales_to_binary_units(self):
        self.assertEqual(console.human_size(500), "500.0 B")
        self.assertEqual(console.human_size(1024), "1.0 KB")
        self.assertEqual(console.human_size(2048), "2.0 KB")
        self.assertEqual(console.human_size(1024**2), "1.0 MB")
        self.assertEqual(console.human_size(1024**3), "1.0 GB")
        self.assertEqual(console.human_size(1024**4), "1.0 TB")

    def test_human_size_falls_through_to_petabytes(self):
        self.assertEqual(console.human_size(2 * 1024**5), "2.0 PB")

    def test_table_returns_table_with_columns(self):
        t = console.table("Title", ["A", "B"])
        self.assertEqual([c.header for c in t.columns], ["A", "B"])

    def test_error_writes_to_stderr_not_stdout(self):
        out, err = io.StringIO(), io.StringIO()
        console.configure(no_color=True, quiet=False, out_file=out, err_file=err)
        console.error("boom")
        self.assertIn("boom", err.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_quiet_suppresses_status_but_not_error(self):
        out, err = io.StringIO(), io.StringIO()
        console.configure(no_color=True, quiet=True, out_file=out, err_file=err)
        console.status("scanning")
        console.error("bad")
        self.assertNotIn("scanning", err.getvalue())
        self.assertIn("bad", err.getvalue())
