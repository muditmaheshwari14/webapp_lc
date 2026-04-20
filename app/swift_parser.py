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


def _search_group(pattern, text: str, group: int = 1, default: str = "") -> str:
    match = pattern.search(text)
    if match:
        return match.group(group).strip()
    return default


def _normalize_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = text.replace("`", "'")

    # remove trailing spaces on each line
    text = "\n".join(line.rstrip() for line in text.splitlines())

    return text.strip()


def parse_sender(text: str) -> Dict[str, str]:
    match = SENDER_BLOCK_PATTERN.search(text)
    if not match:
        return {"bic": "", "name": "", "location": ""}

    return {
        "bic": match.group(1).strip(),
        "name": " ".join(match.group(2).split()),
        "location": " ".join(match.group(3).split()),
    }


def parse_receiver(text: str) -> Dict[str, str]:
    match = RECEIVER_BLOCK_PATTERN.search(text)
    if not match:
        return {"bic": "", "name": "", "location": ""}

    return {
        "bic": match.group(1).strip(),
        "name": " ".join(match.group(2).split()),
        "location": " ".join(match.group(3).split()),
    }


def parse_swift_blocks(text: str) -> Dict[str, str]:
    return {
        "block_1": _search_group(BLOCK_1_PATTERN, text),
        "block_2": _search_group(BLOCK_2_PATTERN, text),
        "block_3": _search_group(BLOCK_3_PATTERN, text),
        "block_5": _search_group(BLOCK_5_PATTERN, text),
    }


def parse_swift_fields(text: str) -> Dict[str, str]:
    """
    Capture full SWIFT field values until the next field tag.

    Supports both formats:
      :46A:
      value...
      :47A:
      value...

    and:
      46A :
      value...
      47A :
      value...

    Returns:
        {
            "20": "...",
            "46A": "full multiline value",
            "47A": "full multiline value",
        }
    """
    text = _normalize_text(text)

    if not text:
        return {}

    # Matches field tags in either style:
    #   :20:
    #   :46A:
    #   20 :
    #   46A :
    field_tag_pattern = re.compile(
        r"(?m)^(?:\s*:?\s*)([0-9]{2}[A-Z]?)\s*:\s*(.*)$"
    )

    matches = list(field_tag_pattern.finditer(text))
    fields: Dict[str, str] = {}

    if not matches:
        return fields

    for i, match in enumerate(matches):
        code = match.group(1).strip()

        # first line content after the field tag
        first_line_value = (match.group(2) or "").strip()

        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        remaining_block = text[start_pos:end_pos]

        if first_line_value:
            raw_value = first_line_value + "\n" + remaining_block
        else:
            raw_value = remaining_block

        raw_value = raw_value.strip()

        # normalize internal spacing a bit but DO NOT truncate
        raw_value = "\n".join(line.rstrip() for line in raw_value.splitlines()).strip()

        fields[code] = format_field_for_display(code, raw_value)

    return fields


def parse_top_advice_details(text: str) -> Dict[str, str]:
    return {
        "advice_date": _search_group(ADVICE_DATE_PATTERN, text),
        "our_ref": _search_group(OUR_REF_PATTERN, text),
        "top_amount": _search_group(TOP_AMOUNT_PATTERN, text),
        "top_beneficiary": _search_group(TOP_BENEFICIARY_PATTERN, text),
        "top_issuing_bank": _search_group(TOP_ISSUING_BANK_PATTERN, text),
        "top_issuing_bank_lc_no": _search_group(TOP_ISSUING_BANK_LC_NO_PATTERN, text),
    }


def parse_message_metadata(text: str) -> Dict[str, str]:
    return {
        "message_number": _search_group(MESSAGE_NUMBER_PATTERN, text),
        "message_type": _search_group(MESSAGE_TYPE_PATTERN, text),
        "priority": _search_group(PRIORITY_PATTERN, text),
        "message_output_reference": _search_group(MESSAGE_OUTPUT_REF_PATTERN, text),
        "correspondent_input_reference": _search_group(CORRESPONDENT_INPUT_REF_PATTERN, text),
        "swift_output": _search_group(SWIFT_OUTPUT_PATTERN, text),
    }


def parse_lc_document(text: str) -> Dict[str, Any]:
    text = _normalize_text(text)

    fields = parse_swift_fields(text)
    sender = parse_sender(text)
    receiver = parse_receiver(text)
    swift_blocks = parse_swift_blocks(text)
    metadata = parse_message_metadata(text)
    advice = parse_top_advice_details(text)

    return {
        "advice_details": advice,
        "message_metadata": metadata,
        "sender": sender,
        "receiver": receiver,
        "swift_blocks": swift_blocks,
        "fields": fields,
    }