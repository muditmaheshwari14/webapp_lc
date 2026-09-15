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


ATTACHED_BARE_BULLET_TEXT = """
Our Reference No.: DCAUKA013343
:46A:Documents Required
:   :+ 3 ORIGINALS OF COMMERCIAL INVOICE ISSUED BY THE BENEFICIARY
:   :BASED ON NET WEIGHT.
:   :+ FULL SET (3/3) OF ORIGINAL CLEAN SHIPPED ON BOARD BILL OF
:   :LADING, MARKED 'FREIGHT PREPAID' AND SHOWING HS CODE: 72044900.
:   :+ 3 ORIGINALS OF DETAILED PACKING LIST ISSUED BY THE BENEFICIARY
:   :SHOWING CONTAINER NO., CONTAINER SIZE, SEAL NO., TOTAL
:   :CONTAINER, TOTAL NET WEIGHT OF EACH CONTAINER AND TOTAL NET
HSBC UK Bank plc, Global Trade Solutions
T: 0345 600 1522
Registered in England number 09928412. Registered Office: 1 Centenary Square, Birmingham B1 1HQ
HSBC UK Bank plc is authorised by the Prudential Regulation Authority and regulated by the Financial
Conduct Authority and Prudential Regulation Authority
Page 4 / 6
DCAUKA013343
:   :WEIGHT OF EACH SHIPMENT.
:   :+ 03 ORIGINALS CERTIFICATE OF ORIGIN ISSUED BY THE BENEFICIARY.
:   :+ 03 ORIGINALS CERTIFICATE OF QUALITY AND QUANTITY ISSUED BY THE
:   :BENEFICIARY CERTIFYING THAT THE CARGO COMPLIES WITH ARTICLE 1 OF
:   :THE CONTRACT NO. TMS-NBA-01.2026 DATED 25TH AUG, 2026
:   :+ 03 ORIGINALS CERTIFICATE OF NON-RADIOACTIVE MATERIAL AND
:   :NON-EXPLOSIVE ISSUED BY THE BENEFICIARY
:47A:Additional Conditions
:   :+ DOCUMENTS TO BE PRESENTED WITHIN 21 DAYS AFTER THE SHIPMENT
:   :DATE BUT WITHIN THE VALIDITY OF THE CREDIT.
:   :+ ALL DOCUMENTS MUST BE PRESENTED IN TRIPLICATE (UNLESS
:   :OTHERWISE STATED) INDICATED CREDIT NUMBER AND ISSUING DATE.
:   :+ ALL DOCUMENTS MUST BE ISSUED IN ENGLISH
:   :+ T.T.R NOT ALLOWED
:   :+ THIRD PARTY DOCUMENTS ALLOWED EXCEPT COMMERCIAL INVOICE AND
:   :DRAFT.
:   :+ BL MUST SHOW FULL PARTICULARS OF THE SHIPPING AGENT IN VIETNAM.
:   :+ PARTIAL SHIPMENT ALLOWED (MAX 2 SHIPMENTS)
:   :+ BL MUST BE ISSUED BY THE SHIPPING LINE OR SHIPPING LINE'S
:   :AGENT.
:   :+ DRAFT MUST BE ISSUED FOR EACH SET OF SHIPPING DOCUMENT.
:   :+ ALL DOCUMENT DATE (EXCEPT B/L) MUST BE ON OR BEFORE THE ON
:   :BOARD DATE
:   :+ APPLICANT ADDRESS:BLOCK A5, D2 STREET, DAT CUOC INDUSTRIAL
:   :PARK (ZONE B), BAC TAN UYEN COMMUNE, HO CHI MINH CITY, VIETNAM
:   :+ ONE ADDITIONAL COPY/PHOTOCOPY OF ALL REQUIRED DOCUMENTS TO BE
:   :PRESENTED FOR L/C ISSUING BANK'S FILE.
:   :+ A DISCREPANCY FEE OF USD88.00 SHOULD BE DEDUCTED FROM THE
:   :PROCEEDS FOR ALL DOCUMENTS NEGOTIATED WITH DISCREPANCIES.
:   :+ IF THE TRANSACTION IS WITHIN THE SCOPE OF ANY OF THE
:   :REGULATIONS OF EUROPEAN UNION, UNITED NATIONS OR OFAC CONCERNING
:   :RESTRICTIVE MEASURES AND SANCTIONS.
:   :+ DOCUMENTS OR SWIFT MESSAGE ARRIVING AT ISSUING BANK'S COUNTER
:   :LATER THAN 03.00 PM ON BANKING DAY WILL BE RECEIVED NEXT DAY.
:71D:Charges
:   :BANKING CHARGES OUTSIDE VIETNAM ARE FOR ACCOUNT OF BENEFICIARY
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

    def test_splits_attached_lc_bare_bullets_and_preserves_page_continuation(self):
        parsed = parse_lc_document(ATTACHED_BARE_BULLET_TEXT)

        documents = field_value_to_points("46A", parsed["fields"]["46A"])
        conditions = field_value_to_points("47A", parsed["fields"]["47A"])

        self.assertEqual(len(documents), 6)
        self.assertEqual(len(conditions), 15)
        self.assertIn("BASED ON NET WEIGHT.", documents[0])
        self.assertIn("TOTAL NET WEIGHT OF EACH SHIPMENT.", documents[2])
        self.assertNotIn("Page 4 / 6", documents[2])
        self.assertEqual(conditions[3], "+ T.T.R NOT ALLOWED")
        self.assertTrue(conditions[-1].startswith("+ DOCUMENTS OR SWIFT MESSAGE"))


if __name__ == "__main__":
    unittest.main()
