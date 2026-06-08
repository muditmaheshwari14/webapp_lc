from typing import Dict, Any
import re

from regex_patterns import (
    MESSAGE_NUMBER_PATTERN,
    MESSAGE_TYPE_PATTERN,
    PRIORITY_PATTERN,
    MESSAGE_OUTPUT_REF_PATTERN,
    CORRESPONDENT_INPUT_REF_PATTERN,
    SWIFT_OUTPUT_PATTERN,
    SENDER_BLOCK_PATTERN,
    RECEIVER_BLOCK_PATTERN,
    BLOCK_1_PATTERN,
    BLOCK_2_PATTERN,
    BLOCK_3_PATTERN,
    BLOCK_5_PATTERN,
    ADVICE_DATE_PATTERN,
    OUR_REF_PATTERN,
    TOP_AMOUNT_PATTERN,
    TOP_BENEFICIARY_PATTERN,
    TOP_ISSUING_BANK_PATTERN,
    TOP_ISSUING_BANK_LC_NO_PATTERN,
)
from text_cleaner import format_field_for_display


UK_STYLE_DATE_PATTERN = re.compile(r"(?m)^\s*([A-Za-z]+ \d{1,2}, \d{4})\s*$")
UK_STYLE_OUR_REF_PATTERN = re.compile(r"Our Reference No\.?\s*:\s*([A-Za-z0-9\/\-_]+)", re.IGNORECASE)
UK_STYLE_DOC_CREDIT_NUMBER_PATTERN = re.compile(
    r"Documentary Credit Number\s*:\s*([A-Za-z0-9\/\-_]+)",
    re.IGNORECASE,
)
UK_STYLE_ISSUING_BANK_PATTERN = re.compile(r"From:\s*(.+)", re.IGNORECASE)
UK_STYLE_SENDER_PATTERN = re.compile(
    r"From:\s*(.+?)\s*\n\s*\(Swift Address:\s*([A-Z0-9]{8,11})\s*\)",
    re.IGNORECASE | re.DOTALL,
)
UK_STYLE_RECEIVER_PATTERN = re.compile(
    r"(?m)^\s*TO\s*:\s*RECEIVER\s*$\s*\n\s*([A-Z0-9]{8,11})\s*$",
    re.IGNORECASE,
)
UK_STYLE_MESSAGE_TYPE_PATTERN = re.compile(r"\bSWIFT\s+O?([0-9]{3})\b", re.IGNORECASE)
FIELD_TAG_PATTERN = re.compile(r"^\s*:?\s*([0-9]{2}[A-Z]?)\s*:\s*(.*)$")
UK_STYLE_FIELD_TAG_PATTERN = re.compile(r"^\s*:\s*([0-9]{2}[A-Z]?|TO)\s*:\s*(.*)$")
UK_STYLE_CONTINUATION_PATTERN = re.compile(r"^\s*:\s*:\s*(.*)$")
IGNORABLE_FIELD_LINE_PATTERNS = (
    re.compile(r"^HSBC UK Bank plc, Global Trade Solutions$", re.IGNORECASE),
    re.compile(r"^T:\s*[\d+\s]+$", re.IGNORECASE),
    re.compile(r"^Registered in England number\b", re.IGNORECASE),
    re.compile(r"^HSBC UK Bank plc is authorised\b", re.IGNORECASE),
    re.compile(r"^Conduct Authority and Prudential Regulation Authority$", re.IGNORECASE),
    re.compile(r"^Page\s+\d+\s*/\s*\d+$", re.IGNORECASE),
)
MESSAGE_END_PATTERNS = (
    re.compile(r"^-}\{5:\{", re.IGNORECASE),
    re.compile(r"^\*\*\*End of Message\*\*\*$", re.IGNORECASE),
    re.compile(r"^Here ends the foregoing cable\.?$", re.IGNORECASE),
)


def _search_group(pattern, text: str, group: int = 1, default: str = "") -> str:
    match = pattern.search(text)
    if match:
        return match.group(group).strip()
    return default


def _search_with_fallbacks(patterns, text: str, group: int = 1, default: str = "") -> str:
    for pattern in patterns:
        value = _search_group(pattern, text, group=group, default="")
        if value:
            return value
    return default


def _normalize_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = text.replace("`", "'")

    normalized_lines = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            normalized_lines.append("")
            continue

        continuation_match = UK_STYLE_CONTINUATION_PATTERN.fullmatch(stripped)
        if continuation_match:
            normalized_lines.append(continuation_match.group(1).strip())
            continue

        field_match = UK_STYLE_FIELD_TAG_PATTERN.fullmatch(stripped)
        if field_match:
            code = field_match.group(1).strip()
            remainder = (field_match.group(2) or "").strip()
            normalized_lines.append(f"{code} : {remainder}".rstrip())
            continue

        normalized_lines.append(line)

    # remove trailing spaces on each line
    text = "\n".join(line.rstrip() for line in normalized_lines)

    return text.strip()


def parse_sender(text: str) -> Dict[str, str]:
    match = SENDER_BLOCK_PATTERN.search(text)
    if match:
        return {
            "bic": match.group(1).strip(),
            "name": " ".join(match.group(2).split()),
            "location": " ".join(match.group(3).split()),
        }

    uk_match = UK_STYLE_SENDER_PATTERN.search(text)
    if not uk_match:
        return {"bic": "", "name": "", "location": ""}

    return {
        "bic": uk_match.group(2).strip(),
        "name": " ".join(uk_match.group(1).split()),
        "location": "",
    }


def parse_receiver(text: str) -> Dict[str, str]:
    match = RECEIVER_BLOCK_PATTERN.search(text)
    if match:
        return {
            "bic": match.group(1).strip(),
            "name": " ".join(match.group(2).split()),
            "location": " ".join(match.group(3).split()),
        }

    uk_match = UK_STYLE_RECEIVER_PATTERN.search(text)
    if not uk_match:
        return {"bic": "", "name": "", "location": ""}

    return {
        "bic": uk_match.group(1).strip(),
        "name": "",
        "location": "",
    }


def parse_swift_blocks(text: str) -> Dict[str, str]:
    return {
        "block_1": _search_group(BLOCK_1_PATTERN, text),
        "block_2": _search_group(BLOCK_2_PATTERN, text),
        "block_3": _search_group(BLOCK_3_PATTERN, text),
        "block_5": _search_group(BLOCK_5_PATTERN, text),
    }


def parse_swift_fields(text: str) -> Dict[str, str]:
    """Capture full SWIFT field values until the next field tag."""
    text = _normalize_text(text)

    if not text:
        return {}

    fields: Dict[str, str] = {}
    current_code = ""
    current_lines: list[str] = []

    def commit_current_field() -> None:
        nonlocal current_code, current_lines

        if not current_code:
            return

        raw_value = "\n".join(current_lines).strip()
        fields[current_code] = format_field_for_display(current_code, raw_value)
        current_code = ""
        current_lines = []

    ignored_line_values = {
        _normalize_text(value)
        for value in (
            parse_top_advice_details(text).get("our_ref", ""),
        )
        if _normalize_text(value)
    }

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if any(pattern.match(stripped) for pattern in MESSAGE_END_PATTERNS):
            commit_current_field()
            break

        match = FIELD_TAG_PATTERN.match(line)
        if match:
            commit_current_field()
            current_code = match.group(1).strip()
            first_line_value = (match.group(2) or "").strip()
            current_lines = [first_line_value] if first_line_value else []
            continue

        if not current_code:
            continue

        if not stripped:
            if current_lines and current_lines[-1] != "":
                current_lines.append("")
            continue

        if stripped in ignored_line_values:
            continue

        if any(pattern.match(stripped) for pattern in IGNORABLE_FIELD_LINE_PATTERNS):
            continue

        current_lines.append(stripped)

    commit_current_field()

    return fields


def parse_top_advice_details(text: str) -> Dict[str, str]:
    return {
        "advice_date": _search_with_fallbacks(
            (ADVICE_DATE_PATTERN, UK_STYLE_DATE_PATTERN),
            text,
        ),
        "our_ref": _search_with_fallbacks(
            (OUR_REF_PATTERN, UK_STYLE_OUR_REF_PATTERN),
            text,
        ),
        "top_amount": _search_group(TOP_AMOUNT_PATTERN, text),
        "top_beneficiary": _search_group(TOP_BENEFICIARY_PATTERN, text),
        "top_issuing_bank": _search_with_fallbacks(
            (TOP_ISSUING_BANK_PATTERN, UK_STYLE_ISSUING_BANK_PATTERN),
            text,
        ),
        "top_issuing_bank_lc_no": _search_with_fallbacks(
            (TOP_ISSUING_BANK_LC_NO_PATTERN, UK_STYLE_DOC_CREDIT_NUMBER_PATTERN),
            text,
        ),
    }


def parse_message_metadata(text: str) -> Dict[str, str]:
    return {
        "message_number": _search_group(MESSAGE_NUMBER_PATTERN, text),
        "message_type": _search_with_fallbacks(
            (MESSAGE_TYPE_PATTERN, UK_STYLE_MESSAGE_TYPE_PATTERN),
            text,
        ),
        "priority": _search_group(PRIORITY_PATTERN, text),
        "message_output_reference": _search_group(MESSAGE_OUTPUT_REF_PATTERN, text),
        "correspondent_input_reference": _search_group(CORRESPONDENT_INPUT_REF_PATTERN, text),
        "swift_output": _search_group(SWIFT_OUTPUT_PATTERN, text),
    }


def parse_lc_document(text: str) -> Dict[str, Any]:
    text = _normalize_text(text)

    advice = parse_top_advice_details(text)
    fields = parse_swift_fields(text)
    sender = parse_sender(text)
    receiver = parse_receiver(text)
    swift_blocks = parse_swift_blocks(text)
    metadata = parse_message_metadata(text)

    return {
        "advice_details": advice,
        "message_metadata": metadata,
        "sender": sender,
        "receiver": receiver,
        "swift_blocks": swift_blocks,
        "fields": fields,
    }
