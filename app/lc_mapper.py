from typing import Dict, Any, List
import pandas as pd
import re

from field_names import FIELD_NAMES
from text_cleaner import field_value_to_points, get_base_field_code, should_expand_field_rows


FIELD_CODE_SORT_PATTERN = re.compile(r"^([0-9]{2})([A-Z]?)(\d*)$")


def get_field_name(code: str) -> str:
    return FIELD_NAMES.get(get_base_field_code(code), "Unknown Field")


def build_value_preview(value: str, max_length: int = 120) -> str:
    preview = value.replace("\n", " | ")
    if len(preview) > max_length:
        return preview[:max_length] + "..."
    return preview


def sort_field_code(code: str):
    normalized_code = str(code).strip()
    match = FIELD_CODE_SORT_PATTERN.fullmatch(normalized_code)
    if match:
        return (
            int(match.group(1)),
            match.group(2),
            int(match.group(3) or 0),
        )

    num = int("".join([c for c in normalized_code if c.isdigit()]) or 0)
    alpha = "".join([c for c in normalized_code if c.isalpha()])
    return (num, alpha, 0)


def build_summary(parsed: Dict[str, Any]) -> Dict[str, str]:
    fields = parsed.get("fields", {})
    advice = parsed.get("advice_details", {})
    meta = parsed.get("message_metadata", {})
    sender = parsed.get("sender", {})
    receiver = parsed.get("receiver", {})

    return {
        "Advice Date": advice.get("advice_date", ""),
        "Our Ref": advice.get("our_ref", ""),
        "Top Beneficiary": advice.get("top_beneficiary", ""),
        "Top Issuing Bank": advice.get("top_issuing_bank", ""),
        "Top Issuing Bank LC No": advice.get("top_issuing_bank_lc_no", ""),
        "Top Amount": advice.get("top_amount", ""),
        "Message Number": meta.get("message_number", ""),
        "Message Type": meta.get("message_type", ""),
        "Priority": meta.get("priority", ""),
        "Swift Output": meta.get("swift_output", ""),
        "Message Output Reference": meta.get("message_output_reference", ""),
        "Correspondent Input Reference": meta.get("correspondent_input_reference", ""),
        "Sender BIC": sender.get("bic", ""),
        "Sender Name": sender.get("name", ""),
        "Sender Location": sender.get("location", ""),
        "Receiver BIC": receiver.get("bic", ""),
        "Receiver Name": receiver.get("name", ""),
        "Receiver Location": receiver.get("location", ""),
        "20 - Documentary Credit Number": fields.get("20", ""),
        "31C - Date Of Issue": fields.get("31C", ""),
        "31D - Date and Place of Expiry": fields.get("31D", ""),
        "32B - Currency Code, Amount": fields.get("32B", ""),
        "50 - Applicant": fields.get("50", ""),
        "59 - Beneficiary": fields.get("59", ""),
        "44C - Latest Date of Shipment": fields.get("44C", ""),
        "49 - Confirmation Instructions": fields.get("49", ""),
    }


def build_fields_dataframe(parsed: Dict[str, Any], expand_rows: bool = True) -> pd.DataFrame:
    rows: List[Dict[str, str]] = []

    for code, value in parsed.get("fields", {}).items():
        points = field_value_to_points(code, value)

        if expand_rows and should_expand_field_rows(code) and points:
            for idx, point in enumerate(points, start=1):
                rows.append(
                    {
                        "Code": f"{code}{idx}",
                        "Field Name": get_field_name(code),
                        "Value": point,
                        "Value Preview": build_value_preview(point),
                    }
                )
            continue

        if points:
            preview = " | ".join([p.split("\n")[0] for p in points[:2]])
            if len(points) > 2:
                preview += " | ..."
            preview = build_value_preview(preview)
        else:
            preview = build_value_preview(value)

        rows.append(
            {
                "Code": code,
                "Field Name": get_field_name(code),
                "Value": value,
                "Value Preview": preview,
            }
        )

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values(by="Code", key=lambda col: col.map(sort_field_code)).reset_index(drop=True)

    return df


def build_metadata_dataframe(parsed: Dict[str, Any]) -> pd.DataFrame:
    meta = parsed.get("message_metadata", {})
    sender = parsed.get("sender", {})
    receiver = parsed.get("receiver", {})
    advice = parsed.get("advice_details", {})
    blocks = parsed.get("swift_blocks", {})

    rows = [
        {"Section": "Advice", "Field": "Advice Date", "Value": advice.get("advice_date", "")},
        {"Section": "Advice", "Field": "Our Ref", "Value": advice.get("our_ref", "")},
        {"Section": "Advice", "Field": "Top Beneficiary", "Value": advice.get("top_beneficiary", "")},
        {"Section": "Advice", "Field": "Top Issuing Bank", "Value": advice.get("top_issuing_bank", "")},
        {"Section": "Advice", "Field": "Top Issuing Bank LC No", "Value": advice.get("top_issuing_bank_lc_no", "")},
        {"Section": "Advice", "Field": "Top Amount", "Value": advice.get("top_amount", "")},
        {"Section": "Message Metadata", "Field": "Message Number", "Value": meta.get("message_number", "")},
        {"Section": "Message Metadata", "Field": "Message Type", "Value": meta.get("message_type", "")},
        {"Section": "Message Metadata", "Field": "Priority", "Value": meta.get("priority", "")},
        {"Section": "Message Metadata", "Field": "Swift Output", "Value": meta.get("swift_output", "")},
        {"Section": "Message Metadata", "Field": "Message Output Reference", "Value": meta.get("message_output_reference", "")},
        {"Section": "Message Metadata", "Field": "Correspondent Input Reference", "Value": meta.get("correspondent_input_reference", "")},
        {"Section": "Sender", "Field": "BIC", "Value": sender.get("bic", "")},
        {"Section": "Sender", "Field": "Name", "Value": sender.get("name", "")},
        {"Section": "Sender", "Field": "Location", "Value": sender.get("location", "")},
        {"Section": "Receiver", "Field": "BIC", "Value": receiver.get("bic", "")},
        {"Section": "Receiver", "Field": "Name", "Value": receiver.get("name", "")},
        {"Section": "Receiver", "Field": "Location", "Value": receiver.get("location", "")},
        {"Section": "Swift Blocks", "Field": "Block 1", "Value": blocks.get("block_1", "")},
        {"Section": "Swift Blocks", "Field": "Block 2", "Value": blocks.get("block_2", "")},
        {"Section": "Swift Blocks", "Field": "Block 3", "Value": blocks.get("block_3", "")},
        {"Section": "Swift Blocks", "Field": "Block 5", "Value": blocks.get("block_5", "")},
    ]

    return pd.DataFrame(rows)
