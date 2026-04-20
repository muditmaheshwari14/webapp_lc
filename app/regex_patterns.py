import re

# Generic multiline SWIFT field matcher.
# Example:
# 20 : Documentary Credit Number
#   26INSU0201-00423
#
# It captures the field code and everything until the next field code.
SWIFT_FIELD_PATTERN = re.compile(
    r"(?ms)^\s*([0-9]{2}[A-Z]?)\s*:\s*(.*?)(?=^\s*[0-9]{2}[A-Z]?\s*:|\Z)"
)

MESSAGE_NUMBER_PATTERN = re.compile(r"Message\s*#\s*:\s*([A-Za-z0-9]+)", re.IGNORECASE)
MESSAGE_TYPE_PATTERN = re.compile(r"Message\s*Type\s*:\s*([A-Za-z0-9]+)", re.IGNORECASE)

PRIORITY_PATTERN = re.compile(r"Priority\s*:\s*(.+)", re.IGNORECASE)
MESSAGE_OUTPUT_REF_PATTERN = re.compile(r"Message Output Reference\s*:\s*(.+)", re.IGNORECASE)
CORRESPONDENT_INPUT_REF_PATTERN = re.compile(r"Correspondent Input Reference\s*:\s*(.+)", re.IGNORECASE)
SWIFT_OUTPUT_PATTERN = re.compile(r"Swift Output\s*:\s*(.+)", re.IGNORECASE)

SENDER_BLOCK_PATTERN = re.compile(
    r"Sender\s*:\s*([A-Z0-9]+)\s*\n\s*(.*?)\s*\n\s*(.*?)\s*(?=\n\s*Receiver\s*:)",
    re.IGNORECASE | re.DOTALL,
)

RECEIVER_BLOCK_PATTERN = re.compile(
    r"Receiver\s*:\s*([A-Z0-9]+)\s*\n\s*(.*?)\s*\n\s*(.*?)(?=\n[-\s]*Message Text|\n\{1:|\Z)",
    re.IGNORECASE | re.DOTALL,
)

BLOCK_1_PATTERN = re.compile(r"\{1:(.*?)\}")
BLOCK_2_PATTERN = re.compile(r"\{2:(.*?)\}")
BLOCK_3_PATTERN = re.compile(r"\{3:\{(.*?)\}\}")
BLOCK_5_PATTERN = re.compile(r"\{5:\{(.*?)\}\}")

ADVICE_DATE_PATTERN = re.compile(r"Website:\s*.*?\s+(\d{2}-[A-Za-z]{3}-\d{4})", re.IGNORECASE)
OUR_REF_PATTERN = re.compile(r"Our Ref\.\s*([A-Za-z0-9\/\-_]+)", re.IGNORECASE)
TOP_AMOUNT_PATTERN = re.compile(r"Amount:\s*([A-Z]{3}\s*[\d,]+\.\d{2})", re.IGNORECASE)
TOP_BENEFICIARY_PATTERN = re.compile(r"To the Beneficiary:\s*(.+)", re.IGNORECASE)
TOP_ISSUING_BANK_PATTERN = re.compile(r"L/C Issuing Bank:\s*(.+)", re.IGNORECASE)
TOP_ISSUING_BANK_LC_NO_PATTERN = re.compile(r"Issuing Bank L/C No:\s*(.+)", re.IGNORECASE)