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
