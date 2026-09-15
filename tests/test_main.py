import sys
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))


FIELD_48_UI_APP = """
import main

main.load_salesforce_config = lambda secrets: {
    "object_api_name": "Letter_Of_Credit__c",
    "default_create_fields_json": "{}",
}
main.find_duplicate_letter_of_credit_records_from_config = lambda **kwargs: {
    "ok": True,
    "records": [],
}

parsed = {
    "advice_details": {"top_issuing_bank": "TEST BANK"},
    "fields": {
        "20": "LC-001",
        "45A": "STEEL SCRAP CFR PORT QASIM",
        "51A": "TESTBANKXXX",
    },
}

main.render_salesforce_sync_section(
    parsed=parsed,
    document_key="field48-ui-test",
    checklist_points_by_code={"46A": [], "47A": []},
)
"""


class MainAppTests(unittest.TestCase):
    def test_missing_field_48_requires_document_specific_manual_value(self):
        app = AppTest.from_string(FIELD_48_UI_APP, default_timeout=10).run()

        self.assertFalse(app.exception)
        self.assertTrue(
            any(
                "field 48" in error.value.lower()
                and "missing" in error.value.lower()
                for error in app.error
            )
        )
        self.assertEqual(len(app.text_input), 1)
        self.assertTrue(app.button[0].disabled)

        app.text_input[0].input("21/FROM B/L DATE").run()

        self.assertFalse(app.exception)
        self.assertTrue(
            any("manual field 48" in message.value.lower() for message in app.success)
        )
        self.assertFalse(app.button[0].disabled)


if __name__ == "__main__":
    unittest.main()
