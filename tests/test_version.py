import unittest


class TestDeps(unittest.TestCase):
    def test_typer_and_rich_importable(self):
        import rich  # noqa: F401
        import typer  # noqa: F401

    def test_version_is_1_0_0(self):
        import pystou

        self.assertEqual(pystou.__version__, "1.0.0")
