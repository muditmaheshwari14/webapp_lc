from io import BytesIO
import math

import pandas as pd


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def build_summary_csv_bytes(summary: dict) -> bytes:
    df = pd.DataFrame([summary])
    return df.to_csv(index=False).encode("utf-8")


def estimate_wrapped_line_count(value: str, chars_per_line: int = 90) -> int:
    text = str(value or "")
    lines = text.splitlines() or [text]

    wrapped_lines = 0
    for line in lines:
        wrapped_lines += max(1, math.ceil(len(line) / chars_per_line))

    return max(1, wrapped_lines)


def build_excel_workbook_bytes(sheet_data: dict[str, pd.DataFrame]) -> bytes:
    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for sheet_name, df in sheet_data.items():
            df.to_excel(writer, index=False, sheet_name=sheet_name)

        workbook = writer.book
        top_align_format = workbook.add_format({"valign": "top"})
        wrapped_format = workbook.add_format({"text_wrap": True, "valign": "top"})

        for sheet_name, df in sheet_data.items():
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes(1, 0)

            if not df.empty:
                worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)

            for idx, col in enumerate(df.columns):
                max_len = max(len(str(col)), *(len(str(x)) for x in df[col].astype(str))) if not df.empty else len(col)

                if col == "Value":
                    worksheet.set_column(idx, idx, min(max(max_len + 2, 80), 120), wrapped_format)
                else:
                    worksheet.set_column(idx, idx, min(max_len + 2, 40), top_align_format)

            if sheet_name == "Swift Fields" and not df.empty and "Value" in df.columns:
                for row_num, value in enumerate(df["Value"].fillna("").astype(str), start=1):
                    line_count = estimate_wrapped_line_count(value)
                    worksheet.set_row(row_num, min(max(20, line_count * 15), 180))

    output.seek(0)
    return output.read()


def build_excel_bytes(summary_df: pd.DataFrame, metadata_df: pd.DataFrame, fields_df: pd.DataFrame) -> bytes:
    return build_excel_workbook_bytes(
        {
            "Summary": summary_df,
            "Metadata": metadata_df,
            "Swift Fields": fields_df,
        }
    )


def build_metadata_fields_excel_bytes(metadata_df: pd.DataFrame, fields_df: pd.DataFrame) -> bytes:
    return build_excel_workbook_bytes(
        {
            "Metadata": metadata_df,
            "Swift Fields": fields_df,
        }
    )
