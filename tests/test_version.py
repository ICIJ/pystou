import unittest


class TestDeps(unittest.TestCase):
    def test_typer_and_rich_importable(self):
        import rich  # noqa: F401
        import typer  # noqa: F401

    def test_version_is_semver(self):
        # The version is managed by semantic-release; don't hardcode a specific
        # number, just assert it's a valid semantic version string.
        import pystou

        self.assertRegex(pystou.__version__, r"^\d+\.\d+\.\d+")
