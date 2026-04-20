import hashlib
import re

import pandas as pd
import streamlit as st

from pdf_extractor import extract_text_from_pdf_bytes
from text_cleaner import clean_text, field_value_to_points
from swift_parser import parse_lc_document
from lc_mapper import build_summary, build_fields_dataframe, build_metadata_dataframe
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


def strip_leading_point_marker(text: str) -> str:
    cleaned = re.sub(r"^\s*[+*-]?\s*\d{1,2}[.)]\s*", "", str(text or "")).strip()
    return cleaned or str(text or "").strip()


def render_checklist_group(document_key: str, code: str, field_name: str, points: list[str]):
    title = f"{code} - {field_name}"

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
        full_fields_df = build_fields_dataframe(parsed, expand_rows=False)
        metadata_df = build_metadata_dataframe(parsed)
        summary_df = pd.DataFrame([summary])

    st.success("Extraction completed.")

    st.subheader("Summary")
    show_summary_cards(summary)

    st.subheader("Summary Table")
    st.dataframe(summary_df, use_container_width=True)

    st.subheader("Message Metadata / Parties / SWIFT Blocks")
    st.dataframe(metadata_df, use_container_width=True, height=350)

    st.subheader("SWIFT Field-wise Extraction")
    if not fields_df.empty:
        table_df = fields_df.assign(
            Value=fields_df["Value"].fillna("").astype(str).str.replace("\n", " | ", regex=False)
        )[[col for col in ["Code", "Field Name", "Value"] if col in fields_df.columns]]
        max_value_len = int(table_df["Value"].str.len().max()) if not table_df.empty else 0
        value_col_width = min(max(max_value_len * 8, 2200), 12000)

        st.caption("Scroll horizontally in the table to read the full field value.")
        st.dataframe(
            table_df,
            use_container_width=True,
            hide_index=True,
            height=420,
            column_config={
                "Code": st.column_config.TextColumn("Code", width=90),
                "Field Name": st.column_config.TextColumn("Field Name", width=260),
                "Value": st.column_config.TextColumn("Value", width=value_col_width),
            },
        )
    else:
        st.warning("No SWIFT fields found.")

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

    st.subheader("Read Full Field")

    if not full_fields_df.empty:
        # Safer unique display options using row index
        field_options = [
            f"{idx} | {row['Code']} - {row['Field Name']}"
            for idx, row in full_fields_df.iterrows()
        ]

        selected_option = st.selectbox(
            "Choose a field to read in full",
            options=field_options
        )

        selected_idx = int(selected_option.split(" | ", 1)[0])
        selected_row = full_fields_df.loc[selected_idx]

        with st.container(border=True):
            st.markdown(f"**{selected_row['Code']} - {selected_row['Field Name']}**")
            st.text_area(
                "Full field value",
                value=str(selected_row["Value"]),
                height=260,
                disabled=True,
                label_visibility="collapsed",
            )

    st.subheader("Detailed Field View")

    if not full_fields_df.empty:
        for idx, row in full_fields_df.iterrows():
            code = row["Code"]
            field_name = row["Field Name"]
            value = row["Value"]

            with st.expander(f"{idx} | {code} - {field_name}", expanded=False):
                render_field_block(code, field_name, value)

    with st.expander("Raw Extracted Text"):
        st.code(cleaned_text, language=None)

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
