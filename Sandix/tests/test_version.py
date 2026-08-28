import unittest

from sandix import __version__


class VersionTest(unittest.TestCase):
    def test_version_is_defined(self) -> None:
        self.assertTrue(__version__)


if __name__ == "__main__":
    unittest.main()
