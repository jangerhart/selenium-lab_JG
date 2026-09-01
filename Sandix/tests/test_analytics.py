import unittest
from decimal import Decimal
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sandix.analytics import (
    gap_bucket,
    normalize_search_status,
    price_gap,
    price_gap_pct_vs_competitor,
    summarise_price_comparison,
)


class AnalyticsHelpersTest(unittest.TestCase):
    def test_search_status_bucket(self) -> None:
        self.assertEqual(normalize_search_status("OK"), "OK")
        self.assertEqual(normalize_search_status("NOT_FOUND"), "NOT_FOUND")
        self.assertEqual(normalize_search_status("FAILED"), "ERROR")

    def test_price_gap_uses_competitor_as_base(self) -> None:
        self.assertEqual(price_gap(Decimal("110"), Decimal("100")), Decimal("10.0000"))
        self.assertEqual(price_gap_pct_vs_competitor(Decimal("110"), Decimal("100")), Decimal("10.00"))
        self.assertEqual(price_gap(Decimal("90"), Decimal("100")), Decimal("-10.0000"))
        self.assertEqual(price_gap_pct_vs_competitor(Decimal("90"), Decimal("100")), Decimal("-10.00"))

    def test_invalid_competitor_price_is_ignored(self) -> None:
        self.assertIsNone(price_gap(Decimal("110"), Decimal("0")))
        self.assertIsNone(price_gap_pct_vs_competitor(Decimal("110"), Decimal("0")))
        self.assertIsNone(price_gap(Decimal("110"), None))

    def test_gap_bucket(self) -> None:
        self.assertEqual(gap_bucket(Decimal("1")), "SANDIX_MORE_EXPENSIVE")
        self.assertEqual(gap_bucket(Decimal("0")), "EQUAL")
        self.assertEqual(gap_bucket(Decimal("-1")), "SANDIX_CHEAPER")
        self.assertIsNone(gap_bucket(None))

    def test_summary_counts(self) -> None:
        rows = [
            {"price_gap_gross": Decimal("10"), "price_gap_pct_vs_competitor": Decimal("10.00")},
            {"price_gap_gross": Decimal("-5"), "price_gap_pct_vs_competitor": Decimal("-5.00")},
            {"price_gap_gross": Decimal("0"), "price_gap_pct_vs_competitor": Decimal("0.00")},
        ]
        summary = summarise_price_comparison(rows)
        self.assertEqual(summary["matched_product_count"], 3)
        self.assertEqual(summary["sandix_more_expensive_count"], 1)
        self.assertEqual(summary["sandix_cheaper_count"], 1)
        self.assertEqual(summary["equal_price_count"], 1)
        self.assertEqual(summary["average_gap_pct_vs_competitor"], Decimal("1.67"))
        self.assertEqual(summary["max_positive_gap_pct_vs_competitor"], Decimal("10.00"))
        self.assertEqual(summary["max_negative_gap_pct_vs_competitor"], Decimal("-5.00"))


if __name__ == "__main__":
    unittest.main()
