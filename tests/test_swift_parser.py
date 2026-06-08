import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from swift_parser import parse_lc_document
from text_cleaner import field_value_to_points


UK_STYLE_TEXT = """
June 02, 2026
Export New Documentary Credit Advising Advice
Our Reference No.: DCAUKA012718
Documentary Credit Number: TF2614900006
Amount: USD 185,000.00

From: SUMITOMO MITSUI BANKING CORPORATION
      (Swift Address: SMBCSGSGXXX)

SWIFT O700 RECEIVED FROM SWIFT ID SMBCSGSG XXX ON May 29, 2026
:TO : RECEIVER
:   : HBUKGB4BXXX
:   :
:20 :Documentary Credit Number
:   :TF2614900006
:   :
:41D:Available With... By...
:   :ANY BANK IN UNITED KINGDOM
:   :BY NEGOTIATION
:   :
:42D:Drawee
:   :SUMITOMO MITSUI BANKING CORPORATION
:   :88 MARKET STREET, HEX33-01
:   :CAPITASPRING SINGAPORE 048948
:   :
:45A:Description of Goods and/or Services
:   :COMMODITY      : RAILROAD FERROUS SCRAP
:   :QUALITY        : RAIL, STEEL NO. 1-3 AS PER ISRI CODE 27-29
:   :QUANTITY       : 500 MT (+/-5PCT)
:   :UNIT PRICE     : USD370.00/MT
:   :DELIVERY TERMS : CFR CAI MEP PORT, VUNG TAU, VIETNAM (INCOTERMS
:   :                 2010)
:   :
:46A:Documents Required
:   :1. SIGNED COMMERCIAL INVOICE IN 3 ORIGINAL, ISSUED BY
:   :   BENEFICIARY.
:   :2. SIGNED PACKING LIST IN 3 ORIGINAL ISSUED BY BENEFICIARY.
:   :
:47A:Additional Conditions
:   :1. ALL BANKING CHARGES OUTSIDE ISSUING BANK ARE FOR BENEFICIARY
:   :   ACCOUNT.
HSBC UK Bank plc, Global Trade Solutions
T: 0345 600 1522
Registered in England number 09928412. Registered Office: 1 Centenary Square, Birmingham B1 1HQ
HSBC UK Bank plc is authorised by the Prudential Regulation Authority and regulated by the Financial
Conduct Authority and Prudential Regulation Authority
Page 4 / 6
DCAUKA012718
:   :2. THIRD PARTY DOCUMENTS ACCEPTABLE EXCEPT DRAFT AND INVOICE.
:   :
:48 :Period For Presentation in Days
:   :14/DAYS AFTER THE DATE OF SHIPMENT
:   :
:49 :Confirmation Instructions
:   :WITHOUT
:   :
:78 :Instructions to the Paying/Accepting/Negotiating Bank
:   :1) ALL DOCUMENTS ARE TO BE FORWARDED TO US AT
:   :   SUMITOMO MITSUI BANKING CORPORATION
Here ends the foregoing cable.
""".strip()


SHB_STYLE_TEXT = """
Website: www.habibbank.com 31-Mar-2026
Our Ref.
ELC/SHB/141

20   : Documentary Credit Number
       1398LCS260514
78   : Instructions to the Paying/Accepting/Negotiating Bank
       +1) UPON RECEIPT OF COMPLYING PRESENTATIONS.
-}{5:{CHK:EEFFC38E3919}}
 ***End of Message***
""".strip()


class SwiftParserTests(unittest.TestCase):
    def test_parses_uk_split_colon_format_and_ignores_page_footers(self):
        parsed = parse_lc_document(UK_STYLE_TEXT)

        self.assertEqual(parsed["advice_details"]["advice_date"], "June 02, 2026")
        self.assertEqual(parsed["advice_details"]["our_ref"], "DCAUKA012718")
        self.assertEqual(
            parsed["advice_details"]["top_issuing_bank"],
            "SUMITOMO MITSUI BANKING CORPORATION",
        )
        self.assertEqual(parsed["message_metadata"]["message_type"], "700")
        self.assertEqual(parsed["sender"]["bic"], "SMBCSGSGXXX")
        self.assertEqual(parsed["receiver"]["bic"], "HBUKGB4BXXX")
        self.assertEqual(parsed["fields"]["20"], "TF2614900006")
        self.assertEqual(parsed["fields"]["41D"], "ANY BANK IN UNITED KINGDOM BY NEGOTIATION")
        self.assertEqual(
            parsed["fields"]["42D"],
            "SUMITOMO MITSUI BANKING CORPORATION 88 MARKET STREET, HEX33-01 CAPITASPRING SINGAPORE 048948",
        )
        self.assertEqual(parsed["fields"]["48"], "14/DAYS AFTER THE DATE OF SHIPMENT")
        self.assertNotIn("Page 4 / 6", parsed["fields"]["47A"])
        self.assertNotIn("HSBC UK Bank plc", parsed["fields"]["47A"])
        points = field_value_to_points("46A", parsed["fields"]["46A"])
        self.assertEqual(len(points), 2)
        self.assertTrue(
            points[0].startswith(
                "1) SIGNED COMMERCIAL INVOICE IN 3 ORIGINAL, ISSUED BY BENEFICIARY"
            )
        )
        self.assertTrue(
            points[1].startswith(
                "2) SIGNED PACKING LIST IN 3 ORIGINAL ISSUED BY BENEFICIARY"
            )
        )

    def test_stops_at_end_of_message_markers_for_shb_format(self):
        parsed = parse_lc_document(SHB_STYLE_TEXT)

        self.assertEqual(parsed["fields"]["20"], "1398LCS260514")
        self.assertTrue(
            parsed["fields"]["78"].startswith(
                "1) UPON RECEIPT OF COMPLYING PRESENTATIONS"
            )
        )
        self.assertNotIn("CHK:", parsed["fields"]["78"])
        self.assertNotIn("***End of Message***", parsed["fields"]["78"])


if __name__ == "__main__":
    unittest.main()
