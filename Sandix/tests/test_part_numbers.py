import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sandix.part_numbers import (  # noqa: E402
    dedupe_part_numbers_by_base,
    classify_competitor_observation,
    classify_competitor_search_identifier,
    classify_source_identifier,
    split_identifier_tokens,
    strip_variant_suffixes,
)
from sandix.alternatives import split_suffix_cell  # noqa: E402


class PartNumberFilterTest(unittest.TestCase):
    def test_split_identifier_tokens(self) -> None:
        self.assertEqual(split_identifier_tokens("320/A7120 32/925994; 333/E9834A"), ["320/A7120", "32/925994", "333/E9834A"])

    def test_source_suffix_stripping(self) -> None:
        suffixes = ["seal-oem", "oem", "em", "a"]
        self.assertEqual(strip_variant_suffixes("333/H8219seal-oem", suffixes), ("333/H8219", ("seal-oem",)))
        self.assertEqual(strip_variant_suffixes("320/A7120OEM", suffixes), ("320/A7120", ("oem",)))
        self.assertEqual(strip_variant_suffixes("02/100073-C", ["c"]), ("02/100073", ("c",)))
        self.assertEqual(classify_source_identifier("320/A7120OEM", suffixes).variant_scope, "ALTERNATIVE")
        self.assertEqual(classify_source_identifier("320/A7120", suffixes).variant_scope, "ORIGINAL")

    def test_dedupe_part_numbers_by_base(self) -> None:
        suffixes = ["ab", "ad", "ah"]
        self.assertEqual(
            dedupe_part_numbers_by_base(["02/100284AB", "02/100284AD", "02/100284AH", "03/200001"], suffixes),
            ["02/100284", "03/200001"],
        )

    def test_split_suffix_cell(self) -> None:
        self.assertEqual(split_suffix_cell("p, p1"), ["p", "p1"])
        self.assertEqual(split_suffix_cell("a; b, c"), ["a", "b", "c"])

    def test_competitor_search_identifier(self) -> None:
        suffixes = ["seal-oem", "oem", "em", "a"]
        self.assertEqual(classify_competitor_search_identifier("320/A7120OEM", suffixes).classification_reason, "SEARCH_INPUT_SUFFIX")
        self.assertEqual(classify_competitor_search_identifier("320/A7120", suffixes).classification_reason, "SEARCH_INPUT_ORIGINAL")

    def test_competitor_observation_classification(self) -> None:
        suffixes = ["seal-oem", "oem", "em", "a"]
        alt = classify_competitor_observation("320/A7120", "320/A7120-A", "Tesneni JCB", "https://example.test/p/320-a7120-a", suffixes)
        self.assertEqual(alt.variant_scope, "ALTERNATIVE")
        self.assertEqual(alt.classification_reason, "IDENTIFIER_SUFFIX")

        original_keyword = classify_competitor_observation(
            "7247000",
            "7247000-C",
            "Cep 7247000 Original",
            "https://www.profibagr.cz/p/cep-7247000-original",
            suffixes,
        )
        self.assertEqual(original_keyword.variant_scope, "ORIGINAL")
        self.assertEqual(original_keyword.classification_reason, "TEXT_ORIGINAL")

        replacement = classify_competitor_observation("320/A7120", "320/A7120", "Tesneni JCB", "https://example.test/p/320-a7120", suffixes)
        self.assertEqual(replacement.variant_scope, "ALTERNATIVE")
        self.assertEqual(replacement.classification_reason, "NO_ORIGINAL_MARKER")

        unresolved = classify_competitor_observation("320/A7120", "SN70340", "Filter", "https://example.test/p/sn70340", suffixes)
        self.assertEqual(unresolved.variant_scope, "ALTERNATIVE")
        self.assertEqual(unresolved.classification_reason, "NO_ORIGINAL_MARKER")


if __name__ == "__main__":
    unittest.main()
