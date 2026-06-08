import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from text_cleaner import (
    contains_stale_keyword,
    field_value_to_points,
    format_field_for_display,
    split_numbered_points,
)


class SplitNumberedPointsTests(unittest.TestCase):
    def test_contains_stale_keyword_matches_word_case_insensitively(self):
        self.assertTrue(contains_stale_keyword("Presentation of stale documents is not acceptable"))
        self.assertTrue(contains_stale_keyword("STALE DOCUMENTS"))
        self.assertFalse(contains_stale_keyword("installation details"))

    def test_splits_plus_prefixed_inline_points(self):
        value = (
            "+1. SHIPMENT/TRANSSHIPMENT ON ISRAELI AND INDIAN FLAG VESSELS ARE NOT ALLOWED. "
            "+2. DOCUMENTS DATED EARLIER THAN THE DATE OF THIS LETTER OF CREDIT ARE NOT ACCEPTABLE. "
            "+3. INVOICE AND DRAFTS MUST SHOW THIS LETTER OF CREDIT NUMBER. "
            "+4. PRESENTATION OF STALE DOCUMENTS IS NOT ACCEPTABLE."
        )

        points = split_numbered_points(value)

        self.assertEqual(len(points), 4)
        self.assertTrue(points[0].startswith("+1."))
        self.assertTrue(points[-1].startswith("+4."))

    def test_splits_plus_prefixed_parenthesis_points(self):
        value = (
            "+1) BENEFICIARY'S SIGNED COMMERCIAL INVOICE IN TRIPLICATE. "
            "+2) FULL SET OF CLEAN SHIPPED ON BOARD BILLS OF LADING. "
            "+3) PACKING LIST IN TRIPLICATE. "
            "+4) COPIES OF SHIPMENT ADVICE."
        )

        points = split_numbered_points(value)

        self.assertEqual(len(points), 4)
        self.assertTrue(points[1].startswith("+2)"))

    def test_splits_hyphen_numbered_inline_points(self):
        value = (
            "1- BENEFICIARYS SIGNED COMMERCIAL INVOICE. "
            "2- FULL SET OF ORIGINAL CLEAN SHIPPED ON BOARD MARINE BILLS OF LADING. "
            "3- PACKING LIST IN 1 ORIGINAL AND 03 COPIES. "
            "4- INSURANCE IS ARRANGED IN PAKISTAN. "
            "5- CERTIFICATE OF ORIGIN IS REQUIRED. "
            "6-B/L OR SHIPPING CERTIFICATE TO STATE THAT THE CARRYING VESSEL IS SEAWORTHY."
        )

        points = split_numbered_points(value)

        self.assertEqual(len(points), 6)
        self.assertTrue(points[0].startswith("1-"))
        self.assertTrue(points[-1].startswith("6-"))

    def test_keeps_nested_subpoints_inside_parent_point(self):
        value = (
            "+1. COMMERCIAL INVOICE. "
            "+2. INSURANCE ARRANGED BY APPLICANT WITH FOLLOWING DETAILS:\n\n"
            "1) MARINE COVER NOTE NUMBER\n\n"
            "2) NAME OF VESSEL AND DATE OF SAILING\n\n"
            "3) PORT OF LOADING\n\n"
            "4) DESCRIPTION OF GOODS\n\n"
            "5) INVOICE VALUE. "
            "+3. CERTIFICATE OF ORIGIN."
        )

        points = split_numbered_points(value)

        self.assertEqual(len(points), 3)
        self.assertIn("1) MARINE COVER NOTE NUMBER", points[1])
        self.assertTrue(points[2].startswith("+3."))

    def test_field_value_to_points_normalizes_display_numbering(self):
        value = (
            "1- BENEFICIARYS SIGNED COMMERCIAL INVOICE. "
            "2- FULL SET OF ORIGINAL CLEAN SHIPPED ON BOARD MARINE BILLS OF LADING."
        )

        points = field_value_to_points("46A", value)

        self.assertEqual(points, [
            "1) BENEFICIARYS SIGNED COMMERCIAL INVOICE.",
            "2) FULL SET OF ORIGINAL CLEAN SHIPPED ON BOARD MARINE BILLS OF LADING.",
        ])

    def test_formatted_value_round_trips_back_to_points(self):
        raw_value = (
            "+1. DRAFT AND INVOICE MUST INDICATE THIS LC NUMBER. "
            "+2. DOCUMENTS DATED PRIOR TO LC DATE ARE NOT ACCEPTABLE. "
            "+3. NEGOTIATION UNDER RESERVE/GUARANTEE NOT ALLOWED."
        )

        formatted = format_field_for_display("47A", raw_value)
        points = field_value_to_points("47A", formatted)

        self.assertEqual(len(points), 3)
        self.assertEqual(points[0], "1) DRAFT AND INVOICE MUST INDICATE THIS LC NUMBER.")
        self.assertEqual(points[-1], "3) NEGOTIATION UNDER RESERVE/GUARANTEE NOT ALLOWED.")


if __name__ == "__main__":
    unittest.main()
