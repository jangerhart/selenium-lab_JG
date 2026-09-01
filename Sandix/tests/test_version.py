import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sandix import __version__


class VersionTest(unittest.TestCase):
    def test_version_is_defined(self) -> None:
        self.assertTrue(__version__)


if __name__ == "__main__":
    unittest.main()
