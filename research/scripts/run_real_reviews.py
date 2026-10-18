"""Run the RefurbIQ ABSA pipeline on REAL Amazon product reviews.

Source: SetFit/amazon_reviews_multi_en (Multilingual Amazon Reviews Corpus,
Keung et al., EMNLP 2020; Apache-2.0). 200,000 English reviews, balanced
5-star labels (0-4 -> 1-5 stars). Downloaded verbatim to
research/data/real/amazon_train.parquet — no modification of review text.

Honest provenance caveats (kept in every output):
- These are genuine reviews but from Amazon's general marketplace, NOT
  from refurbished-electronics listings on Indian platforms. The paper's
  platform claims still require verified Indian refurbished reviews.
- Aspect detection is keyword-based (same engine as the app, V0.1).
- Sentiment is whole-review (not per-aspect span) — same honesty note
  as src/absa.py.
- The corpus ships with star ratings (1-5), which act as HUMAN
  ground-truth sentiment — a real validation signal the synthetic set
  never had.

Usage:
    python run_real_reviews.py [--n 2000] [--seed 42] [--no-model]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from src.absa import ABSAEngine, ASPECTS  # noqa: E402

PARQUET = REPO / "research" / "data" / "real" / "amazon_train.parquet"
OUT_DIR = REPO / "research" / "data" / "real"

STAR_TO_SENTIMENT = {0: "negative", 1: "negative", 2: "neutral",
                     3: "positive", 4: "positive"}


def sample_reviews(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Stratified sample: equal reviews per star bucket, min length 40
    chars (very short reviews rarely mention aspects)."""
    df = df[df["text"].str.len() >= 40].copy()
    parts = [
        g.sample(n=min(n // 5, len(g)), random_state=seed)
        for _, g in df.groupby("label")
    ]
    out = pd.concat(parts).sample(frac=1.0, random_state=seed)
    return out.reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-model", action="store_true",
                    help="skip neural model, use lexicon fallback (fast)")
    args = ap.parse_args()

    df = pd.read_parquet(PARQUET)
    print(f"loaded {len(df)} real reviews from {PARQUET.name}")

    sample = sample_reviews(df, args.n, args.seed)
    sample["rating"] = sample["label"] + 1  # 1-5 stars

    engine = ABSAEngine(model_name=None) if not args.no_model else None
    if args.no_model:
        engine = ABSAEngine()
        engine.is_available = False  # force lexicon fallback
        engine.pipeline = None

    print(f"sampling {len(sample)} reviews; model: "
          f"{engine.model_name if engine.is_available else 'lexicon fallback'}")

    records = []
    t0 = time.time()
    for i, row in sample.iterrows():
        text = str(row["text"])
        sentiment, confidence = engine.overall_sentiment(text)
        for aspect in engine.extract_aspects(text):
            records.append({
                "review_id": row["id"],
                "aspect": aspect,
                "predicted_sentiment": sentiment.lower(),
                "confidence": round(float(confidence), 4),
                "star_rating": int(row["rating"]),
                "human_sentiment": STAR_TO_SENTIMENT[int(row["label"])],
                "data_origin": "real-amazon-reviews-multi-en",
            })
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(sample)} reviews "
                  f"({time.time() - t0:.0f}s)", flush=True)

    ann = pd.DataFrame(records)
    out_reviews = sample[["id", "text", "rating"]].rename(
        columns={"id": "review_id", "text": "review_text"})
    out_reviews["data_origin"] = "real-amazon-reviews-multi-en"
    out_reviews["source_dataset"] = "SetFit/amazon_reviews_multi_en (Keung et al. 2020)"

    ann_path = OUT_DIR / "real_aspect_annotations.csv"
    rev_path = OUT_DIR / "real_reviews_sample.csv"
    ann.to_csv(ann_path, index=False)
    out_reviews.to_csv(rev_path, index=False)

    # --- validation: predicted vs human (star-derived) sentiment ---
    merged = ann.merge(
        out_reviews[["review_id", "rating"]], on="review_id")
    agree = (merged["predicted_sentiment"] == merged["human_sentiment"]).mean()

    print("\n=== REAL DATA RESULTS ===")
    print(f"reviews sampled:        {len(sample)}")
    print(f"aspect annotations:     {len(ann)}")
    print(f"aspect coverage:        "
          f"{100 * ann[ann.aspect != 'General'].review_id.nunique() / len(sample):.1f}% "
          "of reviews mention >=1 known aspect")
    print(f"predicted-vs-star agreement (per annotation): {agree:.3f}")
    print("\naspect frequency (top):")
    print(ann["aspect"].value_counts().head(12).to_string())
    print("\nsentiment distribution (predicted):")
    print(ann["predicted_sentiment"].value_counts(normalize=True).round(3).to_string())
    print(f"\nsaved: {ann_path.name}, {rev_path.name}")


if __name__ == "__main__":
    main()