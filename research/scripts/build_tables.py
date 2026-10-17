"""Reproducibly build the paper's six results tables from verified outputs.

Every number is computed directly from research/data/*.csv and the model
metric JSON files — no hand-entered values (paper §7: "All table values
must be traceable to the underlying data or model evaluation output.").

Outputs written to research/tables/:
    table1_dataset_profile.csv
    table2_aspect_frequency.csv
    table3_model_performance.csv
    table4_class_specific_recall.csv
    table5_sentiment_by_aspect.csv
    table6_cross_platform.csv

Usage:
    python build_tables.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TABLE_DIR = Path(__file__).resolve().parent.parent / "tables"

ASPECTS = [
    "Product condition",
    "Battery health",
    "Performance",
    "Price and value",
    "Packaging and delivery",
    "Repair and refurbishment quality",
    "Seller and customer service",
    "Returns and refunds",
    "Trust and authenticity",
]
LABELS = ["positive", "neutral", "negative"]


def pct(x: float, total: float) -> float:
    return round(100 * x / total, 1) if total else 0.0


def table1(reviews: pd.DataFrame) -> pd.DataFrame:
    """Dataset profile: verified reviews by marketplace x category."""
    pivot = reviews.pivot_table(
        index="marketplace", columns="product_category", values="review_id",
        aggfunc="count", fill_value=0,
    )
    for col in ("Smartphone", "Laptop", "Camera"):
        if col not in pivot.columns:
            pivot[col] = 0
    pivot = pivot[["Smartphone", "Laptop", "Camera"]]
    pivot["Verified reviews"] = pivot.sum(axis=1)
    pivot = pivot.rename(
        columns={
            "Smartphone": "Smartphone reviews",
            "Laptop": "Laptop reviews",
            "Camera": "Camera reviews",
        }
    )
    pivot = pivot[["Verified reviews", "Smartphone reviews", "Laptop reviews", "Camera reviews"]]
    pivot.loc["Total"] = pivot.sum(axis=0)
    return pivot.reset_index().rename(columns={"index": "Platform", "marketplace": "Platform"})


def table2(annotations: pd.DataFrame) -> pd.DataFrame:
    """Aspect frequency with explicit denominator."""
    counts = annotations["aspect"].value_counts()
    total = int(counts.sum())
    rows = [
        {"Aspect": a, "Number of mentions": int(counts.get(a, 0)),
         "Percentage of all aspect mentions": pct(counts.get(a, 0), total)}
        for a in ASPECTS
    ]
    rows.append({"Aspect": "Total", "Number of mentions": total,
                 "Percentage of all aspect mentions": 100.0})
    return pd.DataFrame(rows)


def load_metrics() -> dict[str, dict]:
    models: dict[str, dict] = {}
    trad = DATA_DIR / "traditional_metrics.json"
    if trad.exists():
        for name, m in json.loads(trad.read_text())["models"].items():
            models[name] = m
    zs = DATA_DIR / "bert_zeroshot_metrics.json"
    if zs.exists():
        m = json.loads(zs.read_text())
        models["BERT-based model (zero-shot)"] = m
    ft = DATA_DIR / "bert_finetuned_metrics.json"
    if ft.exists():
        m = json.loads(ft.read_text())
        models["BERT-based model (fine-tuned DistilBERT)"] = m
    return models


def table3(models: dict[str, dict]) -> pd.DataFrame:
    rows = [
        {
            "Model": name,
            "Accuracy": m["accuracy"],
            "Macro precision": m["macro_precision"],
            "Macro recall": m["macro_recall"],
            "Macro F1-score": m["macro_f1"],
        }
        for name, m in models.items()
    ]
    return pd.DataFrame(rows)


def table4(models: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for name, m in models.items():
        cr = m["class_recall"]
        row = {
            "Model": name,
            "Positive recall": cr.get("positive", float("nan")),
            "Negative recall": cr.get("negative", float("nan")),
            "Neutral recall": cr.get("neutral", float("nan")),
        }
        if "class_support" in m:
            row["Test support (pos/neg/neu)"] = (
                f"{m['class_support'].get('positive', '-')}/"
                f"{m['class_support'].get('negative', '-')}/"
                f"{m['class_support'].get('neutral', '-')}"
            )
        rows.append(row)
    return pd.DataFrame(rows)


def table5(annotations: pd.DataFrame) -> pd.DataFrame:
    """Sentiment distribution WITHIN each aspect (denominator = aspect mentions)."""
    rows = []
    for aspect in ASPECTS:
        sub = annotations[annotations["aspect"] == aspect]
        n = len(sub)
        counts = sub["sentiment"].value_counts()
        rows.append(
            {
                "Aspect": aspect,
                "Positive (%)": pct(counts.get("positive", 0), n),
                "Negative (%)": pct(counts.get("negative", 0), n),
                "Neutral (%)": pct(counts.get("neutral", 0), n),
                "Mentions (denominator)": n,
            }
        )
    return pd.DataFrame(rows)


def table6(annotations: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    """Cross-platform summary: per marketplace, aspect with highest negative
    and positive share among aspects with >= 10 mentions (small-sample guard).
    """
    df = annotations.merge(reviews[["review_id", "marketplace"]], on="review_id")
    rows = []
    for platform in sorted(df["marketplace"].unique()):
        sub = df[df["marketplace"] == platform]
        best_neg, best_pos, best_neg_share, best_pos_share = "-", "-", -1.0, -1.0
        for aspect in ASPECTS:
            a = sub[sub["aspect"] == aspect]
            if len(a) < 10:  # documented small-sample guard
                continue
            neg_share = (a["sentiment"] == "negative").mean()
            pos_share = (a["sentiment"] == "positive").mean()
            if neg_share > best_neg_share:
                best_neg_share, best_neg = neg_share, aspect
            if pos_share > best_pos_share:
                best_pos_share, best_pos = pos_share, aspect
        n_mentions = len(sub)
        rows.append(
            {
                "Platform": platform,
                "Aspect mentions": n_mentions,
                "Aspect with highest negative share": best_neg,
                "Highest negative share (%)": round(100 * best_neg_share, 1) if best_neg_share >= 0 else "-",
                "Aspect with highest positive share": best_pos,
                "Highest positive share (%)": round(100 * best_pos_share, 1) if best_pos_share >= 0 else "-",
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    reviews = pd.read_csv(DATA_DIR / "reviews.csv")
    annotations = pd.read_csv(DATA_DIR / "aspect_annotations.csv")

    outputs = {
        "table1_dataset_profile.csv": table1(reviews),
        "table2_aspect_frequency.csv": table2(annotations),
        "table3_model_performance.csv": table3(load_metrics()),
        "table4_class_specific_recall.csv": table4(load_metrics()),
        "table5_sentiment_by_aspect.csv": table5(annotations),
        "table6_cross_platform.csv": table6(annotations, reviews),
    }
    for name, df in outputs.items():
        path = TABLE_DIR / name
        df.to_csv(path, index=False)
        print(f"--- {name} ---")
        print(df.to_string(index=False))
        print()


if __name__ == "__main__":
    main()