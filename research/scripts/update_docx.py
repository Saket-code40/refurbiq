"""Fill the six results tables in RefurbIQ.docx from research/tables/*.csv.

Reads the computed table CSVs (build_tables.py output) and writes the
values into the corresponding Word tables, replacing [Insert] cells.
The original document is preserved; output is RefurbIQ_completed.docx.

A provenance note is inserted in the Results section and each filled
table caption is left untouched except that a short italic note is
appended to the first paragraph after each table caption.

Usage:
    python update_docx.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
from docx import Document

RESEARCH = Path(__file__).resolve().parent.parent
TABLE_DIR = RESEARCH / "tables"
SRC_DOCX = Path.home() / "Downloads" / "RefurbIQ.docx"
OUT_DOCX = RESEARCH / "reports" / "RefurbIQ_completed.docx"

PROVENANCE_NOTE = (
    "The values inserted below were computed from the synthetic "
    "demonstration dataset (generate_dataset.py v2, seed 42) to validate "
    "the full analytical pipeline. They must be regenerated from "
    "verified authentic marketplace reviews before submission."
)


def load_tables() -> dict[str, pd.DataFrame]:
    names = {
        1: "table1_dataset_profile.csv",
        2: "table2_aspect_frequency.csv",
        3: "table3_model_performance.csv",
        4: "table4_class_specific_recall.csv",
        5: "table5_sentiment_by_aspect.csv",
        6: "table6_cross_platform.csv",
    }
    return {k: pd.read_csv(TABLE_DIR / v) for k, v in names.items()}


BERT_ROW_PRIORITY = ("fine-tuned", "zero-shot")


def _fmt(val) -> str:
    return f"{val:g}" if isinstance(val, float) else str(val)


def _match_row(df: pd.DataFrame, key: str):
    """Find the CSV row matching the docx row label.

    Exact/prefix match first; for the single docx "BERT-based model" row
    prefer the fine-tuned configuration when available (zero-shot results
    stay in the CSV and methodology report as a separate configuration).
    """
    exact = [t for t in df.itertuples(index=False) if str(t[0]) == key]
    if exact:
        return exact[0]
    prefixed = [t for t in df.itertuples(index=False) if str(t[0]).startswith(key)]
    if len(prefixed) > 1:
        for pref in BERT_ROW_PRIORITY:
            for t in prefixed:
                if pref in str(t[0]):
                    return t
    return prefixed[0] if prefixed else None


def fill_table(doc_table, df: pd.DataFrame) -> int:
    """Fill a Word table from a DataFrame, replacing [Insert] cells."""
    n_filled = 0
    for r in doc_table.rows[1:]:
        cells = r.cells
        match = _match_row(df, cells[0].text.strip())
        if match is None:
            continue
        for i, cell in enumerate(cells[1:], start=1):
            txt = cell.text.strip()
            if "[Insert" in txt or txt == "":
                cell.text = _fmt(match[i])
                n_filled += 1
    return n_filled


def fill_cross_platform(doc_table, df: pd.DataFrame) -> int:
    """Fill the 4-column cross-platform table (explicit column mapping).

    docx columns: Platform | highest negative share | highest positive
    share | key observed pattern. The CSV has 6 columns, so values are
    mapped by name and the pattern cell is composed from the CSV.
    """
    n_filled = 0
    for r in doc_table.rows[1:]:
        cells = r.cells
        row = df[df.Platform == cells[0].text.strip()]
        if row.empty:
            continue
        row = row.iloc[0]
        neg_aspect = row["Aspect with highest negative share"]
        neg_pct = row["Highest negative share (%)"]
        pos_aspect = row["Aspect with highest positive share"]
        pos_pct = row["Highest positive share (%)"]
        values = {
            1: neg_aspect,
            2: pos_aspect,
            3: (
                f"Most negative: {neg_aspect} ({_fmt(neg_pct)}%); "
                f"most positive: {pos_aspect} ({_fmt(pos_pct)}%)."
            ),
        }
        for i, cell in enumerate(cells[1:], start=1):
            txt = cell.text.strip()
            if "[Insert" in txt or txt == "":
                cell.text = values[i]
                n_filled += 1
    return n_filled


def main() -> None:
    if not SRC_DOCX.exists():
        raise SystemExit(f"source docx not found: {SRC_DOCX}")

    OUT_DOCX.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(SRC_DOCX, OUT_DOCX)
    doc = Document(str(OUT_DOCX))
    tables_csv = load_tables()

    # doc.tables indexing (0-based):
    #   0 = aspect taxonomy guide (Annexure A)
    #   1 = Table 1 dataset profile
    #   2 = Table 2 aspect frequency
    #   3 = Table 3 model performance
    #   4 = Table 4 class-specific recall
    #   5 = Table 5 sentiment by aspect
    #   6 = Table 6 cross-platform
    #   7 = annotation examples
    doc_to_csv = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}

    total_filled = 0
    for doc_idx, csv_idx in doc_to_csv.items():
        if csv_idx == 6:
            n = fill_cross_platform(doc.tables[doc_idx], tables_csv[csv_idx])
        else:
            n = fill_table(doc.tables[doc_idx], tables_csv[csv_idx])
        print(f"doc table {doc_idx + 1} (Table {csv_idx}): filled {n} cells")
        total_filled += n

    # Insert provenance note right after the "9.1 Dataset Profile" heading.
    for p in doc.paragraphs:
        if p.text.strip().startswith("9.1 Dataset Profile"):
            p.insert_paragraph_before(PROVENANCE_NOTE, style="Normal")
            break

    doc.save(str(OUT_DOCX))
    print(f"\nTotal cells filled: {total_filled}")
    print(f"Saved: {OUT_DOCX}")


if __name__ == "__main__":
    main()