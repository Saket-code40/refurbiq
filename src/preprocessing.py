"""CSV loading and cleaning for refurbished-product reviews.

The text is deliberately kept in natural language (no stemming or aggressive
stopword removal) because the downstream BERT sentiment model expects
natural sentences.
"""

from __future__ import annotations

from typing import Union

import pandas as pd

REQUIRED_COLUMNS = ["review_text", "category"]

OPTIONAL_COLUMNS = [
    "review_id",
    "product_name",
    "brand",
    "rating",
    "platform",
    "seller",
    "country",
    "review_date",
]

SUPPORTED_CATEGORIES = ("Phone", "Laptop", "Camera")

PathOrBuffer = Union[str, "pd.io.common.IOBase"]


def load_data(source: PathOrBuffer) -> pd.DataFrame:
    """Load a reviews CSV from a path or an uploaded file-like object.

    Raises ValueError when required columns are missing so callers can
    surface a friendly message.
    """
    df = pd.read_csv(source)
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")
    return df


def clean_reviews(df: pd.DataFrame) -> pd.DataFrame:
    """Return a cleaned copy of the raw reviews DataFrame.

    Steps: drop rows without review text, de-duplicate, normalise category,
    fill missing optional fields, and coerce the rating column to numeric.
    """
    df = df.copy()

    # Drop empty or whitespace-only reviews.
    df["review_text"] = df["review_text"].astype(str).str.strip()
    df = df[df["review_text"].str.len() > 0]

    # Remove exact duplicate reviews.
    df = df.drop_duplicates(subset="review_text")

    # Normalise category so Phone/phone/PHONE all match downstream.
    df["category"] = (
        df["category"].astype(str).str.strip().str.capitalize()
    )

    # Fill gaps in optional columns; unknown ones are ignored.
    defaults = {
        "product_name": "Unknown",
        "brand": "Unknown",
        "platform": "Unknown",
        "seller": "Unknown",
        "country": "Unknown",
    }
    for col, default in defaults.items():
        if col in df.columns:
            df[col] = df[col].fillna(default)

    if "rating" in df.columns:
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce")

    return df.reset_index(drop=True)


def get_category_counts(df: pd.DataFrame) -> dict:
    """Counts of reviews per category (e.g. {'Phone': 24, 'Laptop': 16})."""
    return df["category"].value_counts().to_dict()


def get_missing_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-column missing-value table used by the upload tab."""
    missing = df.isna().sum()
    return pd.DataFrame(
        {"Column": missing.index, "Missing": missing.values}
    )
