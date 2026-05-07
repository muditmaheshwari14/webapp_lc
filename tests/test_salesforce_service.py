import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from salesforce_service import (
    AUTH_MODE_CLIENT_CREDENTIALS,
    AUTH_MODE_CONNECTED_APP_PASSWORD,
    AUTH_MODE_STATIC_TOKEN,
    DEFAULT_API_VERSION,
    DEFAULT_LOGIN_URL,
    DEFAULT_OBJECT_API_NAME,
    LC_46_OBJECT_API_NAME,
    LC_46_TEXT_FIELD_API_NAME,
    LC_47_OBJECT_API_NAME,
    LC_47_TEXT_FIELD_API_NAME,
    SalesforceConfigError,
    build_checklist_child_record_plans,
    build_duplicate_letter_of_credit_query,
    build_letter_of_credit_payload,
    build_salesforce_query_url,
    build_required_letter_of_credit_payload_fields,
    build_salesforce_sobject_url,
    build_salesforce_token_url,
    create_letter_of_credit_with_checklists_from_config,
    load_salesforce_config,
    parse_additional_fields_json,
)


class SalesforceServiceTests(unittest.TestCase):
    def test_build_payload_maps_our_ref(self):
        parsed = {
            "advice_details": {
                "our_ref": " ELC/SHB/99 ",
            }
        }

        payload = build_letter_of_credit_payload(parsed)

        self.assertEqual(payload, {"Adving_Bank_Reference__c": "ELC/SHB/99"})

    def test_build_checklist_child_record_plans_serializes_selected_points(self):
        plans = build_checklist_child_record_plans(
            lc_number="3001LSI693026",
            selected_points_by_code={
                "46A": ["1. Signed commercial invoice", "2. Packing list"],
                "47A": ["1. Third party documents not acceptable"],
            },
        )

        self.assertEqual(
            plans,
            [
                {
                    "code": "46A",
                    "sequence_number": 1,
                    "name": "3001LSI693026 46A-1",
                    "object_api_name": LC_46_OBJECT_API_NAME,
                    "text_field_api_name": LC_46_TEXT_FIELD_API_NAME,
                    "text_value": "1. Signed commercial invoice",
                },
                {
                    "code": "46A",
                    "sequence_number": 2,
                    "name": "3001LSI693026 46A-2",
                    "object_api_name": LC_46_OBJECT_API_NAME,
                    "text_field_api_name": LC_46_TEXT_FIELD_API_NAME,
                    "text_value": "2. Packing list",
                },
                {
                    "code": "47A",
                    "sequence_number": 1,
                    "name": "3001LSI693026 47A-1",
                    "object_api_name": LC_47_OBJECT_API_NAME,
                    "text_field_api_name": LC_47_TEXT_FIELD_API_NAME,
                    "text_value": "1. Third party documents not acceptable",
                },
            ],
        )

    def test_build_checklist_child_record_plans_skips_blank_points(self):
        plans = build_checklist_child_record_plans(
            lc_number="LC-001",
            selected_points_by_code={
                "46A": ["", "  ", "1. Real point"],
                "47A": [],
            },
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["code"], "46A")
        self.assertEqual(plans[0]["sequence_number"], 3)
        self.assertEqual(plans[0]["text_value"], "1. Real point")

    def test_build_payload_merges_filtered_additional_fields(self):
        parsed = {
            "advice_details": {
                "advice_date": "17-Apr-2026",
                "our_ref": "ELC/SHB/148",
                "top_amount": "USD 212,500.00",
                "top_beneficiary": "Noble Artis Pvt Ltd",
                "top_issuing_bank_lc_no": "3001LSI693026",
            },
            "fields": {
                "20": "3001LSI693026",
                "31C": "260414",
                "31D": "260620UK",
                "32B": "USD212500,",
                "41D": "(Name and Address) ANY BANK IN UK BY NEGOTIATION",
                "44C": "260520",
                "44E": "ANY PORT IN UK/NORWAY",
                "44F": "PORT QASIM, PAKISTAN",
                "45A": "SHREDDED STEEL SCRAP ISRI 211 QTY: 500 MTS AT USD 425/MT ALL OTHER GOODS DETAILS AND SPECIFICATION ARE AS PER BENEFICIARY'S PROFORMA INVOICE NO. SO2604-22761/1 DATED: 08-04-2026 CFR PORT QASIM, PAKISTAN (INCOTERMS-2020)",
                "48": "21/FROM BL DATE BUT WITHIN LC VALIDITY",
                "49": "WITHOUT",
                "50": "NAVEENA STEEL MILLS (PRIVATE) LTD, KARACHI, PAKISTAN",
                "51A": "FAYSPKKAXXX FAYSAL BANK LIMITED KARACHI PK",
                "59": "NOBLE ARTIS PVT LTD 79 COLLEGE ROAD HARROW, LONDON HAI 1BD UNITED KINGDOM",
            },
        }
        extra_fields = {
            "Name": " Test LC 001 ",
            "Empty_Field__c": "   ",
            "Is_Active__c": False,
            "Item_Count__c": 0,
        }

        payload = build_letter_of_credit_payload(parsed, extra_fields)

        self.assertEqual(
            payload,
            {
                "APPLICANT_BANK_F51A__c": "FAYSPKKAXXX FAYSAL BANK LIMITED KARACHI PK",
                "AMOUNT_32B__c": 212500.0,
                "Adving_Bank_Reference__c": "ELC/SHB/148",
                "Advisng_Date__c": "2026-04-17",
                "AVAILABLE_BY_41D__c": "NEGOTIATION",
                "AVAILABLE_WITH_41D__c": "ANY BANK IN UK",
                "BENEFICIARY_59__c": "NOBLE ARTIS PVT LTD 79 COLLEGE ROAD HARROW, LONDON HAI 1BD UNITED KINGDOM",
                "BL_Goods_Description__c": "SHREDDED STEEL SCRAP ISRI 211",
                "BL_Port_of_Discharge__c": "PORT QASIM, PAKISTAN",
                "CONFIRMATION_INSTRUCTIONS_49__c": "WITHOUT",
                "CURRENCY_32B__c": "USD",
                "DATE_OF_EXPIRY__c": "2026-06-20",
                "DESCRIPTION_OF_GOODS_45A__c": "SHREDDED STEEL SCRAP ISRI 211 QTY: 500 MTS AT USD 425/MT ALL OTHER GOODS DETAILS AND SPECIFICATION ARE AS PER BENEFICIARY'S PROFORMA INVOICE NO. SO2604-22761/1 DATED: 08-04-2026 CFR PORT QASIM, PAKISTAN (INCOTERMS-2020)",
                "DISCHARGE_PORT_44F__c": "PORT QASIM, PAKISTAN",
                "DOC_CREDIT_NUMBER_20__c": "3001LSI693026",
                "ISSUE_DATE_31C__c": "2026-04-14",
                "Issuing_Bank__c": "FAYSAL BANK LIMITED KARACHI",
                "LC_Trade_Terms__c": "CFR PORT QASIM, PAKISTAN",
                "LATEST_SHIPMENT_DATE_44C__c": "2026-05-20",
                "LOADING_PORT_44E__c": "ANY PORT IN UK/NORWAY",
                "PERIOD_FOR_PRESENTATION_48__c": 21,
                "PLACE_OF_EXPIRY__c": "UK",
                "SO_Price__c": 425.0,
                "SO_Quantity__c": 500.0,
                "ORDERING_CUSTOMER_50__c": "NAVEENA STEEL MILLS (PRIVATE) LTD, KARACHI, PAKISTAN",
                "Name": "Test LC 001",
                "Is_Active__c": False,
                "Item_Count__c": 0,
            },
        )

    def test_build_required_payload_fields_uses_top_issuing_bank_when_present(self):
        parsed = {
            "advice_details": {
                "top_issuing_bank": "Faysal Bank Ltd",
            },
            "fields": {
                "20": "3001LSI693026",
                "45A": "+ SHREDDED STEEL SCRAP CFR PORT QASIM, PAKISTAN (INCOTERMS-2020)",
                "48": "21/FROM BL DATE BUT WITHIN LC VALIDITY",
                "51A": "FAYSPKKAXXX FAYSAL BANK LIMITED KARACHI PK",
            },
        }

        payload = build_required_letter_of_credit_payload_fields(parsed)

        self.assertEqual(
            payload,
            {
                "APPLICANT_BANK_F51A__c": "FAYSPKKAXXX FAYSAL BANK LIMITED KARACHI PK",
                "DOC_CREDIT_NUMBER_20__c": "3001LSI693026",
                "PERIOD_FOR_PRESENTATION_48__c": 21,
                "Issuing_Bank__c": "Faysal Bank Ltd",
                "LC_Trade_Terms__c": "CFR PORT QASIM, PAKISTAN",
            },
        )

    def test_build_required_payload_fields_falls_back_to_51d(self):
        parsed = {
            "advice_details": {
                "top_issuing_bank": "MCB Bank Limited",
            },
            "fields": {
                "20": "1398LCS260514",
                "45A": "500 MTS OF SHREDDED STEEL SCRAP CFR PORT QASIM PAKISTAN (INCOTERMS 2020)",
                "48": "30/DAYS",
                "51A": "",
                "51D": "Initializing Institution (Name and Address)\nMCB BANK LIMITED.\nCORPORATE MAIN BOULEVARD GULBERG\nLAHORE, PAKISTAN.",
            },
        }

        payload = build_required_letter_of_credit_payload_fields(parsed)

        self.assertEqual(
            payload,
            {
                "APPLICANT_BANK_F51A__c": "Initializing Institution (Name and Address) MCB BANK LIMITED. CORPORATE MAIN BOULEVARD GULBERG LAHORE, PAKISTAN.",
                "DOC_CREDIT_NUMBER_20__c": "1398LCS260514",
                "PERIOD_FOR_PRESENTATION_48__c": 30,
                "Issuing_Bank__c": "MCB Bank Limited",
                "LC_Trade_Terms__c": "CFR PORT QASIM PAKISTAN",
            },
        )

    def test_build_required_payload_fields_falls_back_to_42a_for_issuing_bank(self):
        parsed = {
            "advice_details": {
                "top_issuing_bank": "",
            },
            "fields": {
                "20": "2070/SLC/1072/26",
                "42A": "BKIPPKKAXXX BANKISLAMI PAKISTAN LIMITED KARACHI PK",
                "45A": "SHREDDED STEEL SCRAP CFR PORT QASIM, PAKISTAN (INCOTERMS-2020)",
                "48": "30/DAYS",
            },
        }

        payload = build_required_letter_of_credit_payload_fields(parsed)

        self.assertEqual(
            payload,
            {
                "DOC_CREDIT_NUMBER_20__c": "2070/SLC/1072/26",
                "PERIOD_FOR_PRESENTATION_48__c": 30,
                "Issuing_Bank__c": "BANKISLAMI PAKISTAN LIMITED KARACHI",
                "LC_Trade_Terms__c": "CFR PORT QASIM, PAKISTAN",
            },
        )

    def test_build_duplicate_letter_of_credit_query_uses_only_doc_number(self):
        query = build_duplicate_letter_of_credit_query(
            object_api_name="Letter_Of_Credit__c",
            payload={
                "DOC_CREDIT_NUMBER_20__c": "2070/SLC/1072/26",
                "Adving_Bank_Reference__c": "ELC/SHB/148",
            },
        )

        self.assertIn("FROM Letter_Of_Credit__c", query)
        self.assertIn("DOC_CREDIT_NUMBER_20__c = '2070/SLC/1072/26'", query)
        self.assertNotIn("Adving_Bank_Reference__c = 'ELC/SHB/148'", query)
        self.assertIn("ORDER BY CreatedDate DESC", query)

    def test_build_duplicate_letter_of_credit_query_returns_empty_when_no_keys_exist(self):
        query = build_duplicate_letter_of_credit_query(
            object_api_name="Letter_Of_Credit__c",
            payload={"Adving_Bank_Reference__c": "ELC/SHB/148"},
        )

        self.assertEqual(query, "")

    def test_parse_additional_fields_json_requires_object(self):
        with self.assertRaises(ValueError):
            parse_additional_fields_json('["Name"]')

    def test_parse_additional_fields_json_filters_blank_values(self):
        parsed = parse_additional_fields_json(
            '{"Name": "Test LC", "Empty_Field__c": " ", "Count__c": 0}'
        )

        self.assertEqual(
            parsed,
            {
                "Name": "Test LC",
                "Count__c": 0,
            },
        )

    def test_load_salesforce_config_uses_defaults(self):
        config = load_salesforce_config(
            {
                "SALESFORCE_INSTANCE_URL": "https://example.my.salesforce.com",
                "SALESFORCE_ACCESS_TOKEN": "token-123",
            }
        )

        self.assertEqual(config["auth_mode"], AUTH_MODE_STATIC_TOKEN)
        self.assertEqual(config["object_api_name"], DEFAULT_OBJECT_API_NAME)
        self.assertEqual(config["api_version"], DEFAULT_API_VERSION)
        self.assertEqual(config["default_create_fields_json"], "{}")

    def test_load_salesforce_config_supports_client_credentials(self):
        config = load_salesforce_config(
            {
                "SALESFORCE_AUTH_MODE": "client_credentials",
                "SALESFORCE_CLIENT_ID": "client-id",
                "SALESFORCE_CLIENT_SECRET": "client-secret",
            }
        )

        self.assertEqual(config["auth_mode"], AUTH_MODE_CLIENT_CREDENTIALS)
        self.assertEqual(config["login_url"], DEFAULT_LOGIN_URL)
        self.assertEqual(config["client_id"], "client-id")
        self.assertNotIn("username", config)

    def test_load_salesforce_config_supports_connected_app_credentials(self):
        config = load_salesforce_config(
            {
                "SALESFORCE_AUTH_MODE": "connected_app_password",
                "SALESFORCE_CLIENT_ID": "client-id",
                "SALESFORCE_CLIENT_SECRET": "client-secret",
                "SALESFORCE_USERNAME": "user@example.com",
                "SALESFORCE_PASSWORD": "password123",
                "SALESFORCE_SECURITY_TOKEN": "security-token",
            }
        )

        self.assertEqual(config["auth_mode"], AUTH_MODE_CONNECTED_APP_PASSWORD)
        self.assertEqual(config["login_url"], DEFAULT_LOGIN_URL)
        self.assertEqual(config["client_id"], "client-id")
        self.assertEqual(config["security_token"], "security-token")

    def test_load_salesforce_config_requires_credentials(self):
        with self.assertRaises(SalesforceConfigError):
            load_salesforce_config({})

    def test_load_salesforce_config_requires_complete_connected_app_values(self):
        with self.assertRaises(SalesforceConfigError):
            load_salesforce_config(
                {
                    "SALESFORCE_AUTH_MODE": "connected_app_password",
                    "SALESFORCE_CLIENT_ID": "client-id",
                    "SALESFORCE_USERNAME": "user@example.com",
                }
            )

    def test_load_salesforce_config_requires_client_credentials_values(self):
        with self.assertRaises(SalesforceConfigError):
            load_salesforce_config(
                {
                    "SALESFORCE_AUTH_MODE": "client_credentials",
                    "SALESFORCE_CLIENT_ID": "client-id",
                }
            )

    def test_build_salesforce_sobject_url(self):
        url = build_salesforce_sobject_url(
            "https://example.my.salesforce.com/",
            object_api_name="Letter_Of_Credit__c",
            api_version="v61.0",
        )

        self.assertEqual(
            url,
            "https://example.my.salesforce.com/services/data/v61.0/sobjects/Letter_Of_Credit__c/",
        )

    def test_build_salesforce_query_url(self):
        url = build_salesforce_query_url(
            "https://example.my.salesforce.com/",
            "SELECT Id FROM Letter_Of_Credit__c",
            api_version="v61.0",
        )

        self.assertEqual(
            url,
            "https://example.my.salesforce.com/services/data/v61.0/query?q=SELECT+Id+FROM+Letter_Of_Credit__c",
        )

    def test_build_salesforce_token_url(self):
        url = build_salesforce_token_url("https://login.salesforce.com/")

        self.assertEqual(
            url,
            "https://login.salesforce.com/services/oauth2/token",
        )

    @patch("salesforce_service.create_salesforce_record")
    @patch("salesforce_service.resolve_salesforce_session")
    def test_create_letter_of_credit_with_checklists_from_config_creates_parent_then_children(
        self,
        mock_resolve_salesforce_session,
        mock_create_salesforce_record,
    ):
        mock_resolve_salesforce_session.return_value = {
            "instance_url": "https://example.my.salesforce.com",
            "access_token": "token-123",
        }
        mock_create_salesforce_record.side_effect = [
            {
                "ok": True,
                "status_code": 201,
                "data": {"id": "a001"},
                "record_id": "a001",
                "record_url": "https://example.my.salesforce.com/a001",
            },
            {
                "ok": True,
                "status_code": 201,
                "data": {"id": "a0j1"},
                "record_id": "a0j1",
                "record_url": "https://example.my.salesforce.com/a0j1",
            },
            {
                "ok": True,
                "status_code": 201,
                "data": {"id": "a0k1"},
                "record_id": "a0k1",
                "record_url": "https://example.my.salesforce.com/a0k1",
            },
        ]

        result = create_letter_of_credit_with_checklists_from_config(
            config={
                "object_api_name": "Letter_Of_Credit__c",
                "api_version": "v60.0",
            },
            lc_payload={
                "DOC_CREDIT_NUMBER_20__c": "3001LSI693026",
                "Name": "3001LSI693026",
            },
            selected_points_by_code={
                "46A": ["1. Signed commercial invoice"],
                "47A": ["1. Third party docs not acceptable"],
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["created_child_count"], 2)
        self.assertEqual(result["failed_child_count"], 0)
        self.assertEqual(mock_create_salesforce_record.call_count, 3)

        parent_call = mock_create_salesforce_record.call_args_list[0]
        self.assertEqual(parent_call.kwargs["object_api_name"], "Letter_Of_Credit__c")

        child_46_call = mock_create_salesforce_record.call_args_list[1]
        self.assertEqual(child_46_call.kwargs["object_api_name"], LC_46_OBJECT_API_NAME)
        self.assertEqual(child_46_call.kwargs["payload"]["Letter_Of_Credit__c"], "a001")
        self.assertEqual(
            child_46_call.kwargs["payload"][LC_46_TEXT_FIELD_API_NAME],
            "1. Signed commercial invoice",
        )
        self.assertEqual(child_46_call.kwargs["payload"]["Name"], "3001LSI693026 46A-1")

        child_47_call = mock_create_salesforce_record.call_args_list[2]
        self.assertEqual(child_47_call.kwargs["object_api_name"], LC_47_OBJECT_API_NAME)
        self.assertEqual(child_47_call.kwargs["payload"]["Letter_Of_Credit__c"], "a001")
        self.assertEqual(
            child_47_call.kwargs["payload"][LC_47_TEXT_FIELD_API_NAME],
            "1. Third party docs not acceptable",
        )
        self.assertEqual(child_47_call.kwargs["payload"]["Name"], "3001LSI693026 47A-1")


if __name__ == "__main__":
    unittest.main()
