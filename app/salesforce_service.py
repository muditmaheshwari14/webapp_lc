import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_OBJECT_API_NAME = "Letter_Of_Credit__c"
DEFAULT_API_VERSION = "v60.0"
DEFAULT_LOGIN_URL = "https://login.salesforce.com"
AUTH_MODE_STATIC_TOKEN = "static_token"
AUTH_MODE_CONNECTED_APP_PASSWORD = "connected_app_password"
AUTH_MODE_CLIENT_CREDENTIALS = "client_credentials"
LC_46_OBJECT_API_NAME = "LC_46__c"
LC_47_OBJECT_API_NAME = "LC_47__c"
LC_46_TEXT_FIELD_API_NAME = "Document_Descripion__c"
LC_47_TEXT_FIELD_API_NAME = "Condition_Description__c"
TRADE_TERM_CODES = (
    "EXW",
    "FCA",
    "FAS",
    "FOB",
    "CFR",
    "CIF",
    "CPT",
    "CIP",
    "DPU",
    "DAP",
    "DDP",
)


class SalesforceConfigError(ValueError):
    pass


class SalesforceAuthError(Exception):
    def __init__(self, status_code: int | None, data: Any):
        super().__init__("Salesforce authentication failed.")
        self.status_code = status_code
        self.data = data


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _has_payload_value(value: Any) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    return True


def _filter_payload_fields(fields: Mapping[str, Any] | None) -> dict[str, Any]:
    filtered = {}

    for key, value in (fields or {}).items():
        if not _normalize_text(key):
            continue

        if isinstance(value, str):
            value = value.strip()

        if _has_payload_value(value):
            filtered[str(key).strip()] = value

    return filtered


def _normalize_whitespace(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _first_non_empty(*values: Any) -> str:
    for value in values:
        normalized = _normalize_whitespace(value)
        if normalized:
            return normalized
    return ""


def _get_nested_value(source: Mapping[str, Any] | None, *path: str) -> Any:
    current: Any = source

    for key in path:
        if not isinstance(current, Mapping):
            return ""
        current = current.get(key, "")

    return current


def _extract_first_integer(value: Any) -> int | None:
    match = re.search(r"\d+", _normalize_text(value))
    if not match:
        return None
    return int(match.group())


def _normalize_iso_date(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""

    candidates = [text]
    swift_match = re.search(r"(\d{6})", text)
    if swift_match:
        candidates.insert(0, swift_match.group(1))

    for candidate in candidates:
        for fmt in (
            "%y%m%d",
            "%Y-%m-%d",
            "%d-%b-%Y",
            "%d-%b-%y",
            "%d/%m/%Y",
            "%d/%m/%y",
            "%d-%m-%Y",
            "%d.%m.%Y",
        ):
            try:
                return datetime.strptime(candidate, fmt).date().isoformat()
            except ValueError:
                continue

    return ""


def _extract_expiry_place(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""

    match = re.search(r"^\s*\d{6}\s*(.*)$", text)
    if not match:
        return ""

    return _normalize_whitespace(match.group(1)).strip(" ,.;:-")


def _parse_decimal_number(value: Any) -> float | None:
    text = re.sub(r"[^0-9,.\-]", "", _normalize_text(value))
    if not text:
        return None

    if "." in text and "," in text:
        text = text.replace(",", "")
    elif "," in text:
        if text.count(",") == 1:
            integer_part, fractional_part = text.split(",", 1)
            if len(fractional_part) <= 2:
                text = integer_part + (f".{fractional_part}" if fractional_part else ".0")
            else:
                text = integer_part + fractional_part
        else:
            last_comma_index = text.rfind(",")
            fractional_part = text[last_comma_index + 1 :]
            if len(fractional_part) <= 2:
                text = text[:last_comma_index].replace(",", "") + "." + fractional_part
            else:
                text = text.replace(",", "")

    try:
        return float(text)
    except ValueError:
        return None


def _extract_currency_and_amount(value: Any) -> tuple[str, float | None]:
    text = _normalize_whitespace(value)
    if not text:
        return "", None

    match = re.search(r"([A-Z]{3})\s*([0-9][0-9,.\s]*)", text, re.IGNORECASE)
    if not match:
        return "", None

    currency = match.group(1).upper()
    amount = _parse_decimal_number(match.group(2))
    return currency, amount


def _extract_trade_terms(value: Any) -> str:
    text = _normalize_whitespace(value)
    if not text:
        return ""

    pattern = re.compile(
        r"\b(" + "|".join(TRADE_TERM_CODES) + r")\b\s+(.+?)(?=\s*\(|\s+AS\s+PER\b|$)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return ""

    incoterm = match.group(1).upper()
    remainder = re.sub(r"\s+", " ", match.group(2)).strip(" ,.;:-")
    return f"{incoterm} {remainder}".strip()


def _extract_bank_name_from_bank_block(value: Any) -> str:
    text = _normalize_whitespace(value)
    if not text:
        return ""

    parts = text.split()
    if parts and re.fullmatch(r"[A-Z0-9]{8,11}", parts[0]):
        parts = parts[1:]

    while parts and len(parts[-1]) == 2 and parts[-1].isalpha():
        parts = parts[:-1]

    if parts and parts[-1].upper() in {"PK", "GB", "UK", "AE", "US", "CN", "JP", "IN"}:
        parts = parts[:-1]

    return " ".join(parts).strip(" ,")


def _split_available_with_by(value: Any) -> tuple[str, str]:
    text = _normalize_whitespace(value)
    if not text:
        return "", ""

    text = re.sub(r"^\(?\s*NAME\s+AND\s+ADDRESS\s*\)?\s*", "", text, flags=re.IGNORECASE)
    parts = re.split(r"\bBY\b", text, maxsplit=1, flags=re.IGNORECASE)

    available_with = _normalize_whitespace(parts[0]) if parts else ""
    available_by = _normalize_whitespace(parts[1]) if len(parts) > 1 else ""
    return available_with, available_by


def _extract_hs_code(value: Any) -> str:
    text = _normalize_whitespace(value)
    if not text:
        return ""

    match = re.search(
        r"H\.?\s*S\.?\s*CODE(?:\s*NO)?\s*[:.]?\s*([A-Z0-9./-]+)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return ""

    return match.group(1).strip(" ,.;:-")


def _extract_goods_description(value: Any) -> str:
    text = _normalize_whitespace(value).lstrip("+ ").strip()
    if not text:
        return ""

    stop_patterns = (
        r"\bQTY\b",
        r"\bQUANTITY\b",
        r"\bAT\s+USD\b",
        r"\bAT\s+THE\s+RATE\b",
        r"\bH\.?\s*S\.?\s*CODE\b",
        r"\bALL\s+OTHER\b",
        r"\bAS\s+PER\s+BENEFICIARY\b",
        r"\b(" + "|".join(TRADE_TERM_CODES) + r")\b",
    )

    stop_indexes = []
    for pattern in stop_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            stop_indexes.append(match.start())

    if stop_indexes:
        text = text[: min(stop_indexes)]

    return text.strip(" ,.;:-")


def _extract_quantity(value: Any) -> float | None:
    text = _normalize_whitespace(value)
    if not text:
        return None

    match = re.search(
        r"(?:QTY|QUANTITY)\s*:?\s*([0-9][0-9,]*(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None

    return _parse_decimal_number(match.group(1))


def _extract_unit_price(value: Any) -> float | None:
    text = _normalize_whitespace(value)
    if not text:
        return None

    match = re.search(
        r"(?:AT\s+THE\s+RATE\s+OF\s*|AT\s*)?USD\s*([0-9][0-9,]*(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None

    return _parse_decimal_number(match.group(1))


def build_phase_one_letter_of_credit_payload_fields(parsed: Mapping[str, Any]) -> dict[str, Any]:
    fields = _get_nested_value(parsed, "fields")
    advice_details = _get_nested_value(parsed, "advice_details")

    if not isinstance(fields, Mapping):
        fields = {}
    if not isinstance(advice_details, Mapping):
        advice_details = {}

    payload: dict[str, Any] = {}

    def set_field(field_name: str, value: Any) -> None:
        if not _has_payload_value(value):
            return

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return

        payload[field_name] = value

    doc_credit_number = _first_non_empty(
        fields.get("20", ""),
        advice_details.get("top_issuing_bank_lc_no", ""),
    )
    set_field("DOC_CREDIT_NUMBER_20__c", doc_credit_number)
    set_field("Name", doc_credit_number)

    advice_date = _normalize_iso_date(advice_details.get("advice_date", ""))
    set_field("Advisng_Date__c", advice_date)

    our_ref = _normalize_text(advice_details.get("our_ref", ""))
    set_field("Adving_Bank_Reference__c", our_ref)

    applicant_bank = _first_non_empty(fields.get("51A", ""), fields.get("51D", ""))
    set_field("APPLICANT_BANK_F51A__c", applicant_bank)

    issue_date = _normalize_iso_date(fields.get("31C", ""))
    set_field("ISSUE_DATE_31C__c", issue_date)

    expiry_value = _normalize_text(fields.get("31D", ""))
    set_field("DATE_OF_EXPIRY__c", _normalize_iso_date(expiry_value))
    set_field("PLACE_OF_EXPIRY__c", _extract_expiry_place(expiry_value))

    currency, amount = _extract_currency_and_amount(fields.get("32B", ""))
    if not currency or amount is None:
        fallback_currency, fallback_amount = _extract_currency_and_amount(
            advice_details.get("top_amount", "")
        )
        currency = currency or fallback_currency
        amount = amount if amount is not None else fallback_amount
    set_field("CURRENCY_32B__c", currency)
    set_field("AMOUNT_32B__c", amount)

    set_field(
        "PERCENTAGE_CREDIT_AMOUNT_TOLERANCE_39A__c",
        _normalize_text(fields.get("39A", "")),
    )
    set_field(
        "FORM_OF_DOC_CREDIT_40A__c",
        _normalize_text(fields.get("40A", "")),
    )

    available_with, available_by = _split_available_with_by(fields.get("41D", ""))
    set_field("AVAILABLE_WITH_41D__c", available_with)
    set_field("AVAILABLE_BY_41D__c", available_by)

    drawee = _normalize_whitespace(fields.get("42A", ""))
    set_field("DRAWEE_42A__c", drawee)
    set_field("DRAFTS_AT_42C__c", _normalize_text(fields.get("42C", "")))
    set_field("PARTIAL_SHIPMENTS_43P__c", _normalize_text(fields.get("43P", "")))
    set_field("TRANSSHIPMENT_43T__c", _normalize_text(fields.get("43T", "")))
    set_field("FINAL_DESTINATION_44B__c", _normalize_whitespace(fields.get("44B", "")))
    set_field("LATEST_SHIPMENT_DATE_44C__c", _normalize_iso_date(fields.get("44C", "")))
    set_field("LOADING_PORT_44E__c", _normalize_whitespace(fields.get("44E", "")))

    discharge_port = _normalize_whitespace(fields.get("44F", ""))
    set_field("DISCHARGE_PORT_44F__c", discharge_port)
    set_field("BL_Port_of_Discharge__c", discharge_port)

    description_of_goods = _normalize_whitespace(fields.get("45A", ""))
    set_field("DESCRIPTION_OF_GOODS_45A__c", description_of_goods)
    set_field("HS_CODE_45A__c", _extract_hs_code(description_of_goods))
    set_field("LC_Trade_Terms__c", _extract_trade_terms(description_of_goods))
    set_field("SO_Price__c", _extract_unit_price(description_of_goods))
    set_field("SO_Quantity__c", _extract_quantity(description_of_goods))
    set_field("BL_Goods_Description__c", _extract_goods_description(description_of_goods))

    presentation_period = _extract_first_integer(fields.get("48", ""))
    set_field("PERIOD_FOR_PRESENTATION_48__c", presentation_period)
    set_field(
        "CONFIRMATION_INSTRUCTIONS_49__c",
        _normalize_text(fields.get("49", "")),
    )
    set_field("ORDERING_CUSTOMER_50__c", _normalize_whitespace(fields.get("50", "")))

    beneficiary = _first_non_empty(
        fields.get("59", ""),
        advice_details.get("top_beneficiary", ""),
    )
    set_field("BENEFICIARY_59__c", beneficiary)

    set_field("REIMBURSEMENT_BANK_53A__c", _normalize_whitespace(fields.get("53A", "")))

    issuing_bank = _normalize_whitespace(advice_details.get("top_issuing_bank", ""))
    if not issuing_bank:
        issuing_bank = _extract_bank_name_from_bank_block(
            _first_non_empty(fields.get("51A", ""), fields.get("51D", ""), fields.get("42A", ""))
        )
    set_field("Issuing_Bank__c", issuing_bank)

    return payload


def build_required_letter_of_credit_payload_fields(parsed: Mapping[str, Any]) -> dict[str, Any]:
    phase_one_payload = build_phase_one_letter_of_credit_payload_fields(parsed)
    required_field_names = (
        "APPLICANT_BANK_F51A__c",
        "DOC_CREDIT_NUMBER_20__c",
        "PERIOD_FOR_PRESENTATION_48__c",
        "Issuing_Bank__c",
        "LC_Trade_Terms__c",
    )
    return {
        field_name: phase_one_payload[field_name]
        for field_name in required_field_names
        if field_name in phase_one_payload
    }


def parse_additional_fields_json(raw_json: str) -> dict[str, Any]:
    text = _normalize_text(raw_json)
    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for additional Salesforce fields: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Additional Salesforce fields must be a JSON object.")

    return _filter_payload_fields(parsed)


def build_letter_of_credit_payload(
    parsed: Mapping[str, Any],
    extra_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_phase_one_letter_of_credit_payload_fields(parsed)
    payload.update(_filter_payload_fields(extra_fields))
    return payload


def _build_checklist_child_record_name(
    lc_number: Any,
    code: str,
    sequence_number: int,
    max_length: int = 80,
) -> str:
    suffix = f" {code}-{sequence_number}"
    base_name = _normalize_text(lc_number)

    if not base_name:
        return suffix.strip()[:max_length]

    available_length = max_length - len(suffix)
    if available_length <= 0:
        return suffix.strip()[:max_length]

    trimmed_base = base_name[:available_length].rstrip(" -|")
    if not trimmed_base:
        return suffix.strip()[:max_length]

    return f"{trimmed_base}{suffix}"


def build_checklist_child_record_plans(
    lc_number: Any,
    selected_points_by_code: Mapping[str, list[str]] | None,
) -> list[dict[str, Any]]:
    object_config = {
        "46A": {
            "object_api_name": LC_46_OBJECT_API_NAME,
            "text_field_api_name": LC_46_TEXT_FIELD_API_NAME,
        },
        "47A": {
            "object_api_name": LC_47_OBJECT_API_NAME,
            "text_field_api_name": LC_47_TEXT_FIELD_API_NAME,
        },
    }

    plans: list[dict[str, Any]] = []

    for code in ("46A", "47A"):
        config = object_config[code]
        for sequence_number, point in enumerate((selected_points_by_code or {}).get(code, []), start=1):
            point_text = str(point or "").strip()
            if not point_text:
                continue

            plans.append(
                {
                    "code": code,
                    "sequence_number": sequence_number,
                    "name": _build_checklist_child_record_name(
                        lc_number=lc_number,
                        code=code,
                        sequence_number=sequence_number,
                    ),
                    "object_api_name": config["object_api_name"],
                    "text_field_api_name": config["text_field_api_name"],
                    "text_value": point_text,
                }
            )

    return plans


def build_salesforce_sobject_url(
    instance_url: str,
    object_api_name: str = DEFAULT_OBJECT_API_NAME,
    api_version: str = DEFAULT_API_VERSION,
) -> str:
    normalized_instance = _normalize_text(instance_url).rstrip("/")
    normalized_object = _normalize_text(object_api_name) or DEFAULT_OBJECT_API_NAME
    normalized_version = _normalize_text(api_version) or DEFAULT_API_VERSION
    return f"{normalized_instance}/services/data/{normalized_version}/sobjects/{normalized_object}/"


def build_salesforce_query_url(
    instance_url: str,
    soql: str,
    api_version: str = DEFAULT_API_VERSION,
) -> str:
    normalized_instance = _normalize_text(instance_url).rstrip("/")
    normalized_version = _normalize_text(api_version) or DEFAULT_API_VERSION
    return (
        f"{normalized_instance}/services/data/{normalized_version}/query?"
        f"{urlencode({'q': soql})}"
    )


def build_salesforce_token_url(login_url: str = DEFAULT_LOGIN_URL) -> str:
    normalized_login_url = _normalize_text(login_url).rstrip("/") or DEFAULT_LOGIN_URL
    return f"{normalized_login_url}/services/oauth2/token"


def _normalize_auth_mode(value: Any) -> str:
    normalized = _normalize_text(value).lower().replace("-", "_").replace(" ", "_")

    aliases = {
        "token": AUTH_MODE_STATIC_TOKEN,
        "access_token": AUTH_MODE_STATIC_TOKEN,
        "connected_app": AUTH_MODE_CONNECTED_APP_PASSWORD,
        "username_password": AUTH_MODE_CONNECTED_APP_PASSWORD,
        "password": AUTH_MODE_CONNECTED_APP_PASSWORD,
        "clientcredential": AUTH_MODE_CLIENT_CREDENTIALS,
        "client_credentials_flow": AUTH_MODE_CLIENT_CREDENTIALS,
    }

    return aliases.get(normalized, normalized)


def load_salesforce_config(secrets: Mapping[str, Any]) -> dict[str, str]:
    object_api_name = _normalize_text(
        secrets.get("SALESFORCE_OBJECT_API_NAME", DEFAULT_OBJECT_API_NAME)
    ) or DEFAULT_OBJECT_API_NAME
    api_version = _normalize_text(
        secrets.get("SALESFORCE_API_VERSION", DEFAULT_API_VERSION)
    ) or DEFAULT_API_VERSION
    default_create_fields_json = _normalize_text(
        secrets.get("SALESFORCE_DEFAULT_CREATE_FIELDS_JSON", "{}")
    ) or "{}"

    instance_url = _normalize_text(secrets.get("SALESFORCE_INSTANCE_URL", ""))
    access_token = _normalize_text(secrets.get("SALESFORCE_ACCESS_TOKEN", ""))
    client_id = _normalize_text(secrets.get("SALESFORCE_CLIENT_ID", ""))
    client_secret = _normalize_text(secrets.get("SALESFORCE_CLIENT_SECRET", ""))
    username = _normalize_text(secrets.get("SALESFORCE_USERNAME", ""))
    password = _normalize_text(secrets.get("SALESFORCE_PASSWORD", ""))
    security_token = _normalize_text(secrets.get("SALESFORCE_SECURITY_TOKEN", ""))
    login_url = _normalize_text(secrets.get("SALESFORCE_LOGIN_URL", DEFAULT_LOGIN_URL)) or DEFAULT_LOGIN_URL
    auth_mode_hint = _normalize_auth_mode(secrets.get("SALESFORCE_AUTH_MODE", ""))

    if auth_mode_hint == AUTH_MODE_STATIC_TOKEN or (
        not auth_mode_hint and instance_url and access_token
    ):
        return {
            "auth_mode": AUTH_MODE_STATIC_TOKEN,
            "instance_url": instance_url,
            "access_token": access_token,
            "object_api_name": object_api_name,
            "api_version": api_version,
            "default_create_fields_json": default_create_fields_json,
        }

    if auth_mode_hint == AUTH_MODE_CLIENT_CREDENTIALS or (
        not auth_mode_hint and client_id and client_secret and not username and not password
    ):
        if not client_id or not client_secret:
            raise SalesforceConfigError(
                "Client credentials auth requires SALESFORCE_CLIENT_ID and "
                "SALESFORCE_CLIENT_SECRET in Streamlit secrets."
            )

        return {
            "auth_mode": AUTH_MODE_CLIENT_CREDENTIALS,
            "login_url": login_url,
            "client_id": client_id,
            "client_secret": client_secret,
            "object_api_name": object_api_name,
            "api_version": api_version,
            "default_create_fields_json": default_create_fields_json,
        }

    oauth_values = [client_id, client_secret, username, password]
    if auth_mode_hint == AUTH_MODE_CONNECTED_APP_PASSWORD or any(oauth_values) or security_token:
        if not all(oauth_values):
            raise SalesforceConfigError(
                "Connected App username-password auth requires SALESFORCE_CLIENT_ID, "
                "SALESFORCE_CLIENT_SECRET, SALESFORCE_USERNAME, and "
                "SALESFORCE_PASSWORD in Streamlit secrets."
            )

        return {
            "auth_mode": AUTH_MODE_CONNECTED_APP_PASSWORD,
            "login_url": login_url,
            "client_id": client_id,
            "client_secret": client_secret,
            "username": username,
            "password": password,
            "security_token": security_token,
            "object_api_name": object_api_name,
            "api_version": api_version,
            "default_create_fields_json": default_create_fields_json,
        }

    raise SalesforceConfigError(
        "Missing Salesforce credentials. Add either SALESFORCE_INSTANCE_URL + "
        "SALESFORCE_ACCESS_TOKEN, SALESFORCE_CLIENT_ID + SALESFORCE_CLIENT_SECRET "
        "for client credentials flow, or Connected App username-password values "
        "(SALESFORCE_CLIENT_ID, SALESFORCE_CLIENT_SECRET, SALESFORCE_USERNAME, "
        "SALESFORCE_PASSWORD, and optionally SALESFORCE_SECURITY_TOKEN)."
    )


def _decode_response_body(raw_body: bytes) -> Any:
    text = raw_body.decode("utf-8", errors="replace").strip()
    if not text:
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


def request_salesforce_access_token(
    login_url: str,
    client_id: str,
    client_secret: str,
    username: str,
    password: str,
    security_token: str = "",
    timeout: int = 30,
) -> dict[str, str]:
    token_url = build_salesforce_token_url(login_url)
    request_body = urlencode(
        {
            "grant_type": "password",
            "client_id": client_id,
            "client_secret": client_secret,
            "username": username,
            "password": f"{password}{security_token}",
        }
    ).encode("utf-8")
    request = Request(
        token_url,
        data=request_body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            data = _decode_response_body(response.read())
    except HTTPError as exc:
        raise SalesforceAuthError(int(exc.code), _decode_response_body(exc.read())) from exc
    except URLError as exc:
        raise SalesforceAuthError(
            None,
            [{"message": str(exc.reason), "errorCode": "CONNECTION_ERROR"}],
        ) from exc

    access_token = _normalize_text(data.get("access_token", "")) if isinstance(data, dict) else ""
    instance_url = _normalize_text(data.get("instance_url", "")) if isinstance(data, dict) else ""

    if not access_token or not instance_url:
        raise SalesforceAuthError(
            None,
            data or [{"message": "Salesforce token response was incomplete.", "errorCode": "INVALID_TOKEN_RESPONSE"}],
        )

    return {
        "instance_url": instance_url,
        "access_token": access_token,
    }


def request_salesforce_client_credentials_token(
    login_url: str,
    client_id: str,
    client_secret: str,
    timeout: int = 30,
) -> dict[str, str]:
    token_url = build_salesforce_token_url(login_url)
    request_body = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    request = Request(
        token_url,
        data=request_body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            data = _decode_response_body(response.read())
    except HTTPError as exc:
        raise SalesforceAuthError(int(exc.code), _decode_response_body(exc.read())) from exc
    except URLError as exc:
        raise SalesforceAuthError(
            None,
            [{"message": str(exc.reason), "errorCode": "CONNECTION_ERROR"}],
        ) from exc

    access_token = _normalize_text(data.get("access_token", "")) if isinstance(data, dict) else ""
    instance_url = _normalize_text(data.get("instance_url", "")) if isinstance(data, dict) else ""

    if not access_token or not instance_url:
        raise SalesforceAuthError(
            None,
            data or [{"message": "Salesforce token response was incomplete.", "errorCode": "INVALID_TOKEN_RESPONSE"}],
        )

    return {
        "instance_url": instance_url,
        "access_token": access_token,
    }


def resolve_salesforce_session(config: Mapping[str, Any], timeout: int = 30) -> dict[str, str]:
    auth_mode = _normalize_text(config.get("auth_mode", ""))

    if auth_mode == AUTH_MODE_STATIC_TOKEN:
        return {
            "instance_url": _normalize_text(config.get("instance_url", "")),
            "access_token": _normalize_text(config.get("access_token", "")),
        }

    if auth_mode == AUTH_MODE_CLIENT_CREDENTIALS:
        return request_salesforce_client_credentials_token(
            login_url=str(config.get("login_url", "")),
            client_id=str(config.get("client_id", "")),
            client_secret=str(config.get("client_secret", "")),
            timeout=timeout,
        )

    if auth_mode == AUTH_MODE_CONNECTED_APP_PASSWORD:
        return request_salesforce_access_token(
            login_url=str(config.get("login_url", "")),
            client_id=str(config.get("client_id", "")),
            client_secret=str(config.get("client_secret", "")),
            username=str(config.get("username", "")),
            password=str(config.get("password", "")),
            security_token=str(config.get("security_token", "")),
            timeout=timeout,
        )

    raise SalesforceConfigError("Unsupported Salesforce authentication mode.")


def _escape_soql_literal(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace("'", "\\'")


def _get_duplicate_match_fields(payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    match_fields = []

    for field_name in ("DOC_CREDIT_NUMBER_20__c",):
        value = payload.get(field_name, "")
        normalized = _normalize_text(value)
        if normalized:
            match_fields.append((field_name, normalized))

    return match_fields


def build_duplicate_letter_of_credit_query(
    object_api_name: str,
    payload: Mapping[str, Any],
    limit: int = 10,
) -> str:
    filters = _get_duplicate_match_fields(payload)
    if not filters:
        return ""

    normalized_object = _normalize_text(object_api_name) or DEFAULT_OBJECT_API_NAME
    where_clause = " OR ".join(
        f"{field_name} = '{_escape_soql_literal(value)}'"
        for field_name, value in filters
    )

    return (
        "SELECT Id, DOC_CREDIT_NUMBER_20__c, Adving_Bank_Reference__c, "
        "Issuing_Bank__c, CreatedDate "
        f"FROM {normalized_object} "
        f"WHERE {where_clause} "
        "ORDER BY CreatedDate DESC "
        f"LIMIT {max(1, int(limit))}"
    )


def query_salesforce_records(
    instance_url: str,
    access_token: str,
    soql: str,
    api_version: str = DEFAULT_API_VERSION,
    timeout: int = 30,
) -> dict[str, Any]:
    url = build_salesforce_query_url(
        instance_url=instance_url,
        soql=soql,
        api_version=api_version,
    )
    request = Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = int(response.status)
            data = _decode_response_body(response.read())
    except HTTPError as exc:
        status_code = int(exc.code)
        data = _decode_response_body(exc.read())
    except URLError as exc:
        return {
            "ok": False,
            "status_code": None,
            "data": [{"message": str(exc.reason), "errorCode": "CONNECTION_ERROR"}],
            "records": [],
        }

    records = data.get("records", []) if isinstance(data, dict) else []
    if not isinstance(records, list):
        records = []

    return {
        "ok": status_code == 200,
        "status_code": status_code,
        "data": data,
        "records": records,
    }


def find_duplicate_letter_of_credit_records_from_config(
    config: Mapping[str, Any],
    payload: Mapping[str, Any],
    timeout: int = 30,
) -> dict[str, Any]:
    match_fields = _get_duplicate_match_fields(payload)
    if not match_fields:
        return {
            "ok": True,
            "status_code": None,
            "data": {},
            "records": [],
            "matched_fields": [],
        }

    soql = build_duplicate_letter_of_credit_query(
        object_api_name=str(config.get("object_api_name", DEFAULT_OBJECT_API_NAME)),
        payload=payload,
    )

    try:
        session = resolve_salesforce_session(config, timeout=timeout)
    except SalesforceAuthError as exc:
        return {
            "ok": False,
            "status_code": exc.status_code,
            "data": exc.data,
            "records": [],
            "matched_fields": [field_name for field_name, _ in match_fields],
        }

    result = query_salesforce_records(
        instance_url=session["instance_url"],
        access_token=session["access_token"],
        soql=soql,
        api_version=str(config.get("api_version", DEFAULT_API_VERSION)),
        timeout=timeout,
    )

    normalized_instance = _normalize_text(session["instance_url"]).rstrip("/")
    normalized_records = []

    for record in result.get("records", []):
        if not isinstance(record, Mapping):
            continue

        record_id = _normalize_text(record.get("Id", ""))
        matched_on = [
            field_name
            for field_name, value in match_fields
            if _normalize_text(record.get(field_name, "")) == value
        ]
        normalized_records.append(
            {
                "Id": record_id,
                "DOC_CREDIT_NUMBER_20__c": _normalize_text(record.get("DOC_CREDIT_NUMBER_20__c", "")),
                "Adving_Bank_Reference__c": _normalize_text(record.get("Adving_Bank_Reference__c", "")),
                "Issuing_Bank__c": _normalize_text(record.get("Issuing_Bank__c", "")),
                "CreatedDate": _normalize_text(record.get("CreatedDate", "")),
                "matched_on": matched_on,
                "record_url": f"{normalized_instance}/{record_id}" if record_id else "",
            }
        )

    return {
        "ok": result.get("ok", False),
        "status_code": result.get("status_code"),
        "data": result.get("data", {}),
        "records": normalized_records,
        "matched_fields": [field_name for field_name, _ in match_fields],
    }


def create_salesforce_record(
    instance_url: str,
    access_token: str,
    object_api_name: str,
    payload: Mapping[str, Any],
    api_version: str = DEFAULT_API_VERSION,
    timeout: int = 30,
) -> dict[str, Any]:
    url = build_salesforce_sobject_url(
        instance_url=instance_url,
        object_api_name=object_api_name,
        api_version=api_version,
    )
    request_body = json.dumps(dict(payload)).encode("utf-8")
    request = Request(
        url,
        data=request_body,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = int(response.status)
            data = _decode_response_body(response.read())
    except HTTPError as exc:
        status_code = int(exc.code)
        data = _decode_response_body(exc.read())
    except URLError as exc:
        return {
            "ok": False,
            "status_code": None,
            "data": [{"message": str(exc.reason), "errorCode": "CONNECTION_ERROR"}],
            "record_id": "",
            "record_url": "",
        }

    record_id = data.get("id", "") if isinstance(data, dict) else ""
    normalized_instance = _normalize_text(instance_url).rstrip("/")

    return {
        "ok": status_code == 201,
        "status_code": status_code,
        "data": data,
        "record_id": record_id,
        "record_url": f"{normalized_instance}/{record_id}" if record_id else "",
    }


def create_salesforce_record_from_config(
    config: Mapping[str, Any],
    payload: Mapping[str, Any],
    timeout: int = 30,
) -> dict[str, Any]:
    try:
        session = resolve_salesforce_session(config, timeout=timeout)
    except SalesforceAuthError as exc:
        return {
            "ok": False,
            "status_code": exc.status_code,
            "data": exc.data,
            "record_id": "",
            "record_url": "",
        }

    return create_salesforce_record(
        instance_url=session["instance_url"],
        access_token=session["access_token"],
        object_api_name=str(config.get("object_api_name", DEFAULT_OBJECT_API_NAME)),
        payload=payload,
        api_version=str(config.get("api_version", DEFAULT_API_VERSION)),
        timeout=timeout,
    )


def create_letter_of_credit_with_checklists_from_config(
    config: Mapping[str, Any],
    lc_payload: Mapping[str, Any],
    selected_points_by_code: Mapping[str, list[str]] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    try:
        session = resolve_salesforce_session(config, timeout=timeout)
    except SalesforceAuthError as exc:
        auth_failure = {
            "ok": False,
            "status_code": exc.status_code,
            "data": exc.data,
            "record_id": "",
            "record_url": "",
        }
        return {
            "ok": False,
            "parent_result": auth_failure,
            "child_results": [],
            "planned_child_records": [],
            "created_child_count": 0,
            "failed_child_count": 0,
        }

    parent_result = create_salesforce_record(
        instance_url=session["instance_url"],
        access_token=session["access_token"],
        object_api_name=str(config.get("object_api_name", DEFAULT_OBJECT_API_NAME)),
        payload=lc_payload,
        api_version=str(config.get("api_version", DEFAULT_API_VERSION)),
        timeout=timeout,
    )

    if not parent_result.get("ok", False):
        return {
            "ok": False,
            "parent_result": parent_result,
            "child_results": [],
            "planned_child_records": [],
            "created_child_count": 0,
            "failed_child_count": 0,
        }

    planned_child_records = build_checklist_child_record_plans(
        lc_number=_first_non_empty(
            lc_payload.get("DOC_CREDIT_NUMBER_20__c", ""),
            lc_payload.get("Name", ""),
        ),
        selected_points_by_code=selected_points_by_code,
    )

    child_results: list[dict[str, Any]] = []
    created_child_count = 0
    failed_child_count = 0
    parent_record_id = _normalize_text(parent_result.get("record_id", ""))

    for plan in planned_child_records:
        child_payload = {
            "Letter_Of_Credit__c": parent_record_id,
            plan["text_field_api_name"]: plan["text_value"],
        }
        if plan.get("name"):
            child_payload["Name"] = plan["name"]

        child_result = create_salesforce_record(
            instance_url=session["instance_url"],
            access_token=session["access_token"],
            object_api_name=str(plan["object_api_name"]),
            payload=child_payload,
            api_version=str(config.get("api_version", DEFAULT_API_VERSION)),
            timeout=timeout,
        )
        child_results.append(
            {
                "code": plan["code"],
                "sequence_number": plan["sequence_number"],
                "object_api_name": plan["object_api_name"],
                "text_field_api_name": plan["text_field_api_name"],
                "name": plan["name"],
                "text_value": plan["text_value"],
                "payload": child_payload,
                **child_result,
            }
        )

        if child_result.get("ok", False):
            created_child_count += 1
        else:
            failed_child_count += 1

    return {
        "ok": parent_result.get("ok", False) and failed_child_count == 0,
        "parent_result": parent_result,
        "child_results": child_results,
        "planned_child_records": planned_child_records,
        "created_child_count": created_child_count,
        "failed_child_count": failed_child_count,
    }
