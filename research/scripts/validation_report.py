"""Validation and data-quality report (paper §7.3, §10 deliverable 7).

Checks row counts, duplicates, missing fields, split integrity, annotation
counts, and model-output consistency, then writes
research/reports/validation_report.md.

Usage:
    python validation_report.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    reviews = pd.read_csv(DATA_DIR / "reviews.csv")
    annotations = pd.read_csv(DATA_DIR / "aspect_annotations.csv")
    split = pd.read_csv(DATA_DIR / "split_assignment.csv")
    preds = pd.read_csv(DATA_DIR / "model_predictions.csv")

    lines: list[str] = []
    add = lines.append

    add("# RefurbIQ Paper — Validation and Data-Quality Report")
    add("")
    add(f"Generated: {date.today().isoformat()}")
    add("")
    add(
        "**Provenance:** all findings below derive from the SYNTHETIC "
        "demonstration dataset produced by `generate_dataset.py v2` "
        "(seed 42). No value in this report is based on authentic "
        "marketplace reviews."
    )
    add("")

    # --- Row counts ---
    add("## 1. Row counts")
    add(f"- reviews.csv: {len(reviews)} rows x {len(reviews.columns)} columns")
    add(f"- aspect_annotations.csv: {len(annotations)} rows x {len(annotations.columns)} columns")
    add(f"- split_assignment.csv: {len(split)} rows (one per annotation)")
    add(f"- model_predictions.csv: {len(preds)} rows")
    n_ann = len(annotations)
    assert len(split) == n_ann, "split assignment must cover every annotation"
    # model_predictions.csv holds the held-out test partition only (paper
    # §7.10: models are compared on identical held-out examples).
    n_test = int((split.partition == "test").sum())
    assert len(preds) == n_test, "predictions must cover every test annotation"
    test_ids = set(split.loc[split.partition == "test", "annotation_id"])
    assert set(preds.annotation_id) <= test_ids, "predictions leaked outside test"
    add(f"- Annotations per review: {n_ann / len(reviews):.2f} on average")
    add(
        f"- model_predictions.csv covers the test partition only "
        f"({n_test} annotations); no prediction rows exist outside it."
    )
    add("")

    # --- Duplicate checks ---
    add("## 2. Duplicate checks (documented dedup rule: exact-text)")
    add(f"- Exact duplicate review texts: {reviews.duplicated(subset='review_text').sum()}")
    add(f"- Duplicate review_ids: {reviews.duplicated(subset='review_id').sum()}")
    add(f"- Duplicate annotation_ids: {annotations.duplicated(subset='annotation_id').sum()}")
    add("")

    # --- Missing fields ---
    add("## 3. Missing fields")
    for name, df in (("reviews", reviews), ("annotations", annotations)):
        missing = df.isna().sum()
        add(f"- {name}: {missing.to_dict()}")
    add(
        "- Note: `source_url` is empty by design for the synthetic demo "
        "(no real URLs exist); it must be populated from the verified "
        "collection log before submission."
    )
    add("")

    # --- Split integrity (leakage control) ---
    add("## 4. Split integrity")
    merged = split.merge(reviews[["review_id"]], on="review_id", validate="many_to_one")
    per_partition = merged.groupby("partition")["review_id"].nunique()
    add(f"- Unique reviews per partition: {per_partition.to_dict()}")
    leak = set(per_partition.index) != {"train", "validation", "test"}
    overlap_reviews = (
        merged.loc[merged.partition == "train", "review_id"].unique(),
        merged.loc[merged.partition == "test", "review_id"].unique(),
    )
    shared = set(overlap_reviews[0]) & set(overlap_reviews[1])
    add(f"- Reviews shared between train and test: {len(shared)} (must be 0)")
    add(f"- Annotation counts per partition: {split.groupby('partition').size().to_dict()}")
    add("- Split was made at review level (stratified on majority sentiment), seed 42.")
    add("")

    # --- Annotation counts and label distribution ---
    add("## 5. Annotation counts")
    add(f"- Total aspect mentions: {n_ann}")
    dist = annotations['sentiment'].value_counts()
    for lab in ("positive", "neutral", "negative"):
        add(f"- {lab}: {int(dist.get(lab, 0))} ({100 * dist.get(lab, 0) / n_ann:.1f}%)")
    flagged = annotations["annotation_status"].str.contains("disagreement").sum()
    add(f"- Simulated annotation-disagreement labels: {int(flagged)} ({100 * flagged / n_ann:.1f}%)")
    add(f"- Aspects covered: {annotations['aspect'].nunique()} of 9")
    add("")

    # --- Model predictions consistency ---
    add("## 6. Model prediction coverage")
    pred_cols = [c for c in preds.columns if c.startswith("pred_")]
    add(f"- Prediction columns: {pred_cols}")
    for c in pred_cols:
        add(f"  - {c}: {preds[c].notna().sum()} predictions")
    add("")

    # --- Arithmetic consistency of totals ---
    add("## 7. Arithmetic consistency")
    add(f"- Sum of per-platform review counts equals total: {reviews['marketplace'].value_counts().sum() == len(reviews)}")
    add(f"- Sum of aspect mentions equals annotation rows: {annotations['aspect'].value_counts().sum() == n_ann}")
    add("")

    add("## 8. Remaining placeholders that cannot yet be filled")
    add("- Any claim about REAL customer sentiment (dataset is synthetic).")
    add("- `source_url` and real `collection_date` per platform.")
    add("- Inter-annotator agreement (Cohen's kappa) — single auto-annotator demo.")
    add("- Fine-tuned BERT row in Tables 3-4 — pending completion of finetune_bert.py run.")
    add("")

    report = "\n".join(lines)
    out = REPORT_DIR / "validation_report.md"
    out.write_text(report)
    print(report)
    print(f"\nReport written to {out}")


if __name__ == "__main__":
    main()