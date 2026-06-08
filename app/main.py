import hashlib
import json
import re

import pandas as pd
import streamlit as st

from pdf_extractor import extract_text_from_pdf_bytes
from text_cleaner import clean_text, contains_stale_keyword, field_value_to_points
from swift_parser import parse_lc_document
from lc_mapper import build_summary, build_fields_dataframe, build_metadata_dataframe
from salesforce_service import (
    SalesforceConfigError,
    build_letter_of_credit_payload,
    create_letter_of_credit_with_checklists_from_config,
    find_duplicate_letter_of_credit_records_from_config,
    load_salesforce_config,
    parse_additional_fields_json,
)
from export_services import (
    dataframe_to_csv_bytes,
    build_summary_csv_bytes,
    build_excel_bytes,
    build_metadata_fields_excel_bytes,
)


st.set_page_config(
    page_title="LC / SWIFT MT700 Extractor",
    layout="wide"
)


POINT_STRUCTURED_CODES = {"45A", "46A", "47A", "71D", "78", "72Z"}
CHECKLIST_CODES = {
    "46A": "Documents Required",
    "47A": "Additional Conditions",
}
REQUIRED_SALESFORCE_FIELDS = [
    "APPLICANT_BANK_F51A__c",
    "DOC_CREDIT_NUMBER_20__c",
    "Issuing_Bank__c",
    "LC_Trade_Terms__c",
    "PERIOD_FOR_PRESENTATION_48__c",
]
DUPLICATE_WARNING_FIELDS = [
    "DOC_CREDIT_NUMBER_20__c",
]


def render_app_styles():
    st.markdown(
        """
<style>
.stApp {
    background:
        radial-gradient(circle at top left, rgba(212, 178, 135, 0.18), transparent 24%),
        linear-gradient(180deg, #fcfaf7 0%, #f4efe8 100%);
}

.block-container {
    max-width: 1480px;
    padding-top: 1.35rem;
    padding-bottom: 3rem;
}

h1, h2, h3 {
    color: #16324a;
    letter-spacing: -0.01em;
}

div[data-testid="stDataFrame"] {
    border: 1px solid rgba(22, 50, 74, 0.10);
    border-radius: 18px;
    overflow: hidden;
    box-shadow: 0 12px 32px rgba(22, 50, 74, 0.05);
}

div[data-testid="stExpander"] {
    border: 1px solid rgba(22, 50, 74, 0.12);
    border-radius: 18px;
    overflow: hidden;
    background: rgba(255, 255, 255, 0.82);
    box-shadow: 0 12px 34px rgba(22, 50, 74, 0.05);
    margin-bottom: 1rem;
}

div[data-testid="stExpander"] summary {
    padding-top: 0.15rem;
    padding-bottom: 0.15rem;
}

div[data-testid="stExpander"] summary:hover {
    background: rgba(164, 93, 52, 0.04);
}

div[data-testid="stCheckbox"] {
    margin-top: 0.15rem;
}

div[data-testid="stCheckbox"] label {
    gap: 0.65rem;
    align-items: flex-start;
}

div[data-testid="stCheckbox"] p {
    color: #17324a;
    font-size: 0.97rem;
    line-height: 1.55;
    margin-top: 0.05rem;
}

div[data-testid="stProgressBar"] > div > div {
    background-color: rgba(164, 93, 52, 0.16);
}

div[data-testid="stProgressBar"] div[role="progressbar"] {
    background: linear-gradient(90deg, #a45d34 0%, #c47d4f 100%);
}

.checklist-overview {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    padding: 1rem 1.1rem;
    border-radius: 18px;
    border: 1px solid rgba(22, 50, 74, 0.10);
    background: rgba(255, 255, 255, 0.80);
    box-shadow: 0 10px 28px rgba(22, 50, 74, 0.04);
    min-height: 120px;
}

.checklist-overview-code {
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #a45d34;
}

.checklist-overview-count {
    font-size: 1.7rem;
    font-weight: 700;
    line-height: 1;
    color: #16324a;
}

.checklist-overview-label {
    color: #5e6f81;
    font-size: 0.95rem;
    line-height: 1.4;
}

.check-index {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 2rem;
    height: 2rem;
    border-radius: 999px;
    background: rgba(164, 93, 52, 0.10);
    color: #8b4a25;
    font-weight: 700;
    font-size: 0.92rem;
    margin-top: 0.12rem;
}

.checklist-progress {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.35rem 0.75rem;
    border-radius: 999px;
    background: rgba(22, 50, 74, 0.06);
    color: #16324a;
    font-size: 0.86rem;
    font-weight: 600;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def show_summary_cards(summary: dict):
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("LC Number", summary.get("20 - Documentary Credit Number", ""))
        st.metric("Advice Date", summary.get("Advice Date", ""))
        st.metric("Amount", summary.get("32B - Currency Code, Amount", "") or summary.get("Top Amount", ""))

    with col2:
        st.metric("Message Type", summary.get("Message Type", ""))
        st.metric("Priority", summary.get("Priority", ""))
        st.metric("Expiry", summary.get("31D - Date and Place of Expiry", ""))

    with col3:
        st.metric("Sender BIC", summary.get("Sender BIC", ""))
        st.metric("Receiver BIC", summary.get("Receiver BIC", ""))
        st.metric("Confirmation", summary.get("49 - Confirmation Instructions", ""))


def render_field_block(code: str, field_name: str, value: str):
    st.markdown(f"### {code} - {field_name}")

    if value is None:
        st.info("No data available.")
        return

    value = str(value).strip()
    points = field_value_to_points(code, value)

    if points:
        for point in points:
            lines = [line.strip() for line in point.splitlines() if line.strip()]
            if not lines:
                continue

            first_line, *rest = lines
            st.markdown(f"**{first_line}**")
            if rest:
                st.markdown("  \n".join(rest))
            st.markdown("")
    else:
        if value:
            st.code(value, language=None)
        else:
            st.info("Empty value")


def get_document_key(cleaned_text: str) -> str:
    return hashlib.md5(cleaned_text.encode("utf-8")).hexdigest()[:12]


def get_checklist_points(parsed: dict, code: str):
    value = str(parsed.get("fields", {}).get(code, "") or "").strip()
    points = field_value_to_points(code, value)

    if points:
        return points

    if value:
        return [value]

    return []


def get_selected_checklist_points(document_key: str, code: str, points: list[str]) -> list[str]:
    selected_points = []

    for idx, point in enumerate(points, start=1):
        if st.session_state.get(f"checklist_{document_key}_{code}_{idx}", False):
            selected_points.append(str(point or "").strip())

    return [point for point in selected_points if point]


def strip_leading_point_marker(text: str) -> str:
    cleaned = re.sub(r"^\s*[+*]?\s*\d{1,2}\s*[.)-]\s*", "", str(text or "")).strip()
    return cleaned or str(text or "").strip()


def initialize_checklist_defaults(document_key: str, code: str, points: list[str]) -> None:
    for idx, point in enumerate(points, start=1):
        checkbox_key = f"checklist_{document_key}_{code}_{idx}"
        if checkbox_key in st.session_state:
            continue

        st.session_state[checkbox_key] = contains_stale_keyword(point)


def render_checklist_group(document_key: str, code: str, field_name: str, points: list[str]):
    title = f"{code} - {field_name}"

    initialize_checklist_defaults(document_key=document_key, code=code, points=points)

    checked_count = sum(
        1 for idx in range(1, len(points) + 1)
        if st.session_state.get(f"checklist_{document_key}_{code}_{idx}", False)
    )
    progress = (checked_count / len(points)) if points else 0.0

    with st.expander(f"{title} ({len(points)} items)", expanded=True):
        if not points:
            st.info(f"No checklist points found for {code} in this LC.")
            return

        meta_col, stat_col = st.columns([6, 2], vertical_alignment="center")
        with meta_col:
            st.caption(f"Checklist extracted from {code} for the current LC")
        with stat_col:
            st.markdown(
                f"<div class='checklist-progress'>{checked_count}/{len(points)} complete</div>",
                unsafe_allow_html=True,
            )

        st.progress(progress)

        for idx, point in enumerate(points, start=1):
            checkbox_key = f"checklist_{document_key}_{code}_{idx}"
            lines = [line.strip() for line in str(point).splitlines() if line.strip()]
            label = strip_leading_point_marker(lines[0]) if lines else f"Point {idx}"
            details = " ".join(lines[1:]).strip() if len(lines) > 1 else ""

            num_col, item_col = st.columns([1, 30], vertical_alignment="top")

            with num_col:
                st.markdown(f"<div class='check-index'>{idx}</div>", unsafe_allow_html=True)

            with item_col:
                st.checkbox(label, key=checkbox_key)
                if details:
                    st.caption(details)

        st.caption(f"Completed: {checked_count}/{len(points)}")


def render_salesforce_sync_section(
    parsed: dict,
    document_key: str,
    checklist_points_by_code: dict[str, list[str]],
):
    st.subheader("Salesforce Sync")

    salesforce_config = None
    additional_fields = {}
    additional_fields_error = ""

    try:
        salesforce_config = load_salesforce_config(st.secrets)
        additional_fields = parse_additional_fields_json(
            salesforce_config.get("default_create_fields_json", "{}")
        )
    except FileNotFoundError:
        st.info(
            "No Streamlit secrets file was found. Add `.streamlit/secrets.toml` "
            "in the app run directory or in your user home `.streamlit` folder "
            "to enable Salesforce sync."
        )
    except SalesforceConfigError as exc:
        st.info(str(exc))
    except ValueError as exc:
        additional_fields_error = str(exc)
        st.error(additional_fields_error)

    payload = build_letter_of_credit_payload(parsed, additional_fields)
    selected_checklist_points_by_code = {
        code: get_selected_checklist_points(document_key, code, points)
        for code, points in checklist_points_by_code.items()
    }
    missing_required_fields = [
        field_name
        for field_name in REQUIRED_SALESFORCE_FIELDS
        if field_name not in payload or payload.get(field_name) in ("", None)
    ]

    if missing_required_fields:
        st.error(
            "Some required Salesforce fields are still missing from the mapped payload: "
            + ", ".join(missing_required_fields)
        )

    duplicate_records = []
    duplicate_signature = json.dumps(
        {
            "object_api_name": (salesforce_config or {}).get("object_api_name", ""),
            "doc_credit_number": payload.get("DOC_CREDIT_NUMBER_20__c", ""),
            "advising_bank_reference": payload.get("Adving_Bank_Reference__c", ""),
        },
        sort_keys=True,
    )

    has_duplicate_lookup_values = any(
        str(payload.get(field_name, "") or "").strip()
        for field_name in DUPLICATE_WARNING_FIELDS
    )

    if salesforce_config is not None and payload and has_duplicate_lookup_values:
        cached_signature = st.session_state.get("salesforce_duplicate_check_signature", "")
        if cached_signature != duplicate_signature:
            with st.spinner("Checking Salesforce for matching Letter of Credit records..."):
                st.session_state["salesforce_duplicate_check_result"] = (
                    find_duplicate_letter_of_credit_records_from_config(
                        config=salesforce_config,
                        payload=payload,
                    )
                )
            st.session_state["salesforce_duplicate_check_signature"] = duplicate_signature

        duplicate_check_result = st.session_state.get("salesforce_duplicate_check_result", {})
        duplicate_records = list(duplicate_check_result.get("records", []))

        if duplicate_check_result.get("ok", False):
            if duplicate_records:
                st.warning(
                    "Salesforce already has Letter of Credit record(s) with the same "
                    "document credit number. Review them below before creating another record."
                )

                duplicate_preview_rows = [
                    {
                        "Record ID": record.get("Id", ""),
                        "Matched On": ", ".join(record.get("matched_on", [])),
                        "DOC_CREDIT_NUMBER_20__c": record.get("DOC_CREDIT_NUMBER_20__c", ""),
                        "Adving_Bank_Reference__c": record.get("Adving_Bank_Reference__c", ""),
                        "Issuing_Bank__c": record.get("Issuing_Bank__c", ""),
                        "CreatedDate": record.get("CreatedDate", ""),
                    }
                    for record in duplicate_records
                ]
                st.dataframe(
                    pd.DataFrame(duplicate_preview_rows),
                    use_container_width=True,
                    hide_index=True,
                )

                for record in duplicate_records:
                    if record.get("record_url"):
                        st.markdown(
                            f"- [Open Salesforce record {record.get('Id', '')}]"
                            f"({record['record_url']})"
                        )
        else:
            st.warning("The Salesforce duplicate check could not be completed.")
            if duplicate_check_result.get("status_code") is not None:
                st.caption(f"HTTP status: {duplicate_check_result['status_code']}")
            st.json(duplicate_check_result.get("data", {}))

    proceed_with_duplicate = True
    if duplicate_records:
        proceed_with_duplicate = st.checkbox(
            "I understand this Letter of Credit may already exist in Salesforce and still want to create another record.",
            key=f"salesforce_duplicate_override_{duplicate_signature}",
        )

    create_disabled = (
        salesforce_config is None
        or bool(additional_fields_error)
        or not payload
        or bool(missing_required_fields)
        or (bool(duplicate_records) and not proceed_with_duplicate)
    )

    if st.button("Create Salesforce Letter of Credit record", disabled=create_disabled):
        with st.spinner("Creating Salesforce record..."):
            result = create_letter_of_credit_with_checklists_from_config(
                config=salesforce_config,
                lc_payload=payload,
                selected_points_by_code=selected_checklist_points_by_code,
            )

        parent_result = result.get("parent_result", {})
        child_results = list(result.get("child_results", []))

        if result["ok"]:
            record_id = parent_result.get("record_id", "")
            success_message = "Salesforce record created successfully."
            if record_id:
                success_message += f" Record ID: {record_id}"
            if child_results:
                success_message += (
                    f" Created {result.get('created_child_count', 0)} related 46A / 47A record(s)."
                )
            st.success(success_message)

            if parent_result.get("record_url"):
                st.markdown(f"[Open record in Salesforce]({parent_result['record_url']})")
        elif parent_result.get("ok", False):
            record_id = parent_result.get("record_id", "")
            st.warning(
                "The parent Letter of Credit record was created, but some related 46A / 47A "
                "records could not be created."
                + (f" Parent Record ID: {record_id}" if record_id else "")
            )

            if parent_result.get("record_url"):
                st.markdown(f"[Open parent record in Salesforce]({parent_result['record_url']})")

            for child_result in child_results:
                if not child_result.get("ok", False):
                    st.caption(
                        f"{child_result.get('object_api_name', '')} "
                        f"{child_result.get('code', '')}-{child_result.get('sequence_number', '')}"
                    )
                    st.json(child_result.get("data", {}))
        else:
            st.error("Salesforce record creation failed.")
            if parent_result.get("status_code") is not None:
                st.caption(f"HTTP status: {parent_result['status_code']}")
            st.json(parent_result.get("data", {}))


def main():
    render_app_styles()

    st.title("Letter of Credit Extractor")
    st.write("Upload a Letter of Credit PDF and extract SWIFT MT700 fields into structured output.")

    uploaded_file = st.file_uploader("Upload LC PDF", type=["pdf"])

    if uploaded_file is None:
        st.info("Please upload a PDF file to begin.")
        return

    pdf_bytes = uploaded_file.read()

    with st.spinner("Extracting text from PDF..."):
        raw_text = extract_text_from_pdf_bytes(pdf_bytes)
        cleaned_text = clean_text(raw_text)

    if not cleaned_text.strip():
        st.error("No text could be extracted from the PDF.")
        return

    with st.spinner("Parsing SWIFT fields and metadata..."):
        parsed = parse_lc_document(cleaned_text)
        document_key = get_document_key(cleaned_text)
        summary = build_summary(parsed)
        fields_df = build_fields_dataframe(parsed, expand_rows=True)
        metadata_df = build_metadata_dataframe(parsed)
        summary_df = pd.DataFrame([summary])

    st.success("Extraction completed.")

    st.subheader("Summary")
    show_summary_cards(summary)

    st.subheader("46A / 47A Checklist")
    st.caption("The checklist is generated from the numbered points found in the uploaded LC.")

    checklist_points_by_code = {
        code: get_checklist_points(parsed, code)
        for code in CHECKLIST_CODES
    }

    overview_cols = st.columns(len(CHECKLIST_CODES))
    for column, (code, field_name) in zip(overview_cols, CHECKLIST_CODES.items()):
        points = checklist_points_by_code[code]
        column.markdown(
            f"""
<div class="checklist-overview">
    <div class="checklist-overview-code">{code}</div>
    <div class="checklist-overview-count">{len(points)}</div>
    <div class="checklist-overview-label">{field_name}</div>
</div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    for code, field_name in CHECKLIST_CODES.items():
        render_checklist_group(
            document_key=document_key,
            code=code,
            field_name=field_name,
            points=checklist_points_by_code[code],
        )

    render_salesforce_sync_section(
        parsed=parsed,
        document_key=document_key,
        checklist_points_by_code=checklist_points_by_code,
    )

    st.subheader("Download Exports")

    fields_export_df = fields_df.drop(columns=["Value Preview"], errors="ignore")
    summary_csv_bytes = build_summary_csv_bytes(summary)
    fields_csv_bytes = dataframe_to_csv_bytes(fields_export_df)
    excel_bytes = build_excel_bytes(summary_df, metadata_df, fields_export_df)
    metadata_fields_excel_bytes = build_metadata_fields_excel_bytes(metadata_df, fields_export_df)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.download_button(
            label="Download Summary CSV",
            data=summary_csv_bytes,
            file_name="lc_summary.csv",
            mime="text/csv"
        )

    with col2:
        st.download_button(
            label="Download Fields CSV",
            data=fields_csv_bytes,
            file_name="lc_fields.csv",
            mime="text/csv"
        )

    with col3:
        st.download_button(
            label="Download Full Excel",
            data=excel_bytes,
            file_name="lc_extracted.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with col4:
        st.download_button(
            label="Metadata + Fields Excel",
            data=metadata_fields_excel_bytes,
            file_name="lc_metadata_fields.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


if __name__ == "__main__":
    main()
