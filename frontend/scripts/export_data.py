"""Export the project's computed outputs to JSON for the website frontend.

Every number shown on the site comes from the project's own output files —
nothing is typed by hand. Re-run this script whenever the research outputs
change:

    python frontend/scripts/export_data.py

Writes frontend/public/data/{stats,models,aspect_sentiment,heatmap}.json.
Any value that cannot be read from the outputs is exported as "N/A".
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
TABLES = ROOT / "research" / "tables"
DATA = ROOT / "research" / "data"
OUT = ROOT / "frontend" / "public" / "data"

ASPECTS_9 = [
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


def na_on_missing(fn):
    """Return fn() or 'N/A' if the source file/value is missing."""
    try:
        return fn()
    except Exception:
        return "N/A"


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def build_stats() -> dict:
    """Stat-card values for the home page."""
    def demo_reviews() -> int:
        return len(load_csv(ROOT / "data" / "raw" / "reviews.csv"))

    def platforms() -> int:
        df = load_csv(TABLES / "table1_dataset_profile.csv")
        return int((df.Platform != "Total").sum())

    def best_accuracy() -> str:
        df = load_csv(TABLES / "table3_model_performance.csv")
        best = df.loc[df.Accuracy.idxmax()]
        return f"{best['Model']} — {best['Accuracy']:.1%} accuracy"

    def annotations() -> int:
        df = load_csv(TABLES / "table2_aspect_frequency.csv")
        return int(df.loc[df.Aspect == "Total", "Number of mentions"].iloc[0])

    return {
        "demoReviews": na_on_missing(demo_reviews),
        "platformsCompared": na_on_missing(platforms),
        "bestModel": na_on_missing(best_accuracy),
        "annotations": na_on_missing(annotations),
        "provenance": (
            "All figures are computed from the project's synthetic "
            "demonstration corpus (research/data) and are not verified "
            "marketplace data."
        ),
    }


def build_models() -> dict:
    """Model comparison chart data: accuracy, macro F1, neutral recall."""
    def inner() -> dict:
        perf = load_csv(TABLES / "table3_model_performance.csv")
        recall = load_csv(TABLES / "table4_class_specific_recall.csv")
        merged = perf.merge(recall[["Model", "Neutral recall"]], on="Model")
        rows = [
            {
                "model": r["Model"],
                "accuracy": round(float(r["Accuracy"]), 4),
                "macroF1": round(float(r["Macro F1-score"]), 4),
                "neutralRecall": round(float(r["Neutral recall"]), 4),
            }
            for r in merged.to_dict("records")
        ]
        return {"models": rows}

    return na_on_missing(inner)


def build_aspect_sentiment() -> dict:
    """Aspect sentiment distribution (Table 5 percentages)."""
    def inner() -> dict:
        df = load_csv(TABLES / "table5_sentiment_by_aspect.csv")
        rows = [
            {
                "aspect": r["Aspect"],
                "positive": float(r["Positive (%)"]),
                "neutral": float(r["Neutral (%)"]),
                "negative": float(r["Negative (%)"]),
                "mentions": int(r["Mentions (denominator)"]),
            }
            for r in df.to_dict("records")
        ]
        return {"aspects": rows}

    return na_on_missing(inner)


def build_heatmap() -> dict:
    """Platform x aspect negative-share heatmap, computed from the raw
    annotation corpus (never hand-entered)."""
    def inner() -> dict:
        ann = load_csv(DATA / "aspect_annotations.csv")
        rev = load_csv(DATA / "reviews.csv")[["review_id", "marketplace"]]
        df = ann.merge(rev, on="review_id")
        platforms = sorted(df.marketplace.unique())

        def neg_share(platform: str, aspect: str):
            sub = df[(df.marketplace == platform) & (df.aspect == aspect)]
            if len(sub) == 0:
                return None
            return round(float((sub.sentiment == "negative").mean()), 4)

        cells = [
            {"platform": p, "aspect": a, "negativeShare": neg_share(p, a)}
            for p in platforms
            for a in ASPECTS_9
        ]
        return {"platforms": platforms, "aspects": ASPECTS_9, "cells": cells}

    return na_on_missing(inner)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    outputs = {
        "stats.json": build_stats(),
        "models.json": build_models(),
        "aspect_sentiment.json": build_aspect_sentiment(),
        "heatmap.json": build_heatmap(),
    }
    for name, payload in outputs.items():
        path = OUT / name
        path.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()