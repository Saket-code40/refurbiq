"""Preprocessing pipeline for RefurbIQ.

Loads raw review CSVs, validates required columns, and produces a clean
DataFrame suitable for BERT-based analysis. Text is kept in natural
language (no stemming / aggressive stopword removal) because BERT
tokenizers expect natural sentences.
"""

from typing import Optional

import pandas as pd

# Columns required for the pipeline to function at all
REQUIRED_COLUMNS = ["review_text", "category"]

# Optional columns the app handles gracefully when missing
OPTIONAL_COLUMNS = [
    "review_id",
    "product_name",
    "rating",
    "platform",
    "country",
    "review_date",
]

SUPPORTED_CATEGORIES = {"phone", "laptop"}


def load_data(path_or_buffer) -> pd.DataFrame:
    """Load a reviews CSV into a DataFrame.

    Accepts a file path string or a file-like buffer (e.g. from
    Streamlit's file_uploader).
    """
    df = pd.read_csv(path_or_buffer)
    return df


def validate_columns(df: pd.DataFrame) -> list[str]:
    """Return a list of missing required column names (empty if valid)."""
    return [col for col in REQUIRED_COLUMNS if col not in df.columns]


def normalize_category(value: str) -> str:
    """Map raw category strings to canonical 'Phone' or 'Laptop'."""
    text = str(value).strip().lower()
    if text in SUPPORTED_CATEGORIES:
        return text.capitalize()
    if "phone" in text or "mobile" in text or "smartphone" in text:
        return "Phone"
    if "laptop" in text or "notebook" in text or "macbook" in text:
        return "Laptop"
    # Default to Phone for unknown categories rather than dropping
    return "Phone"


def clean_reviews(df: pd.DataFrame) -> pd.DataFrame:
    """Clean the raw reviews DataFrame.

    Steps:
    1. Check required columns exist
    2. Remove rows with empty / missing review_text
    3. Remove duplicate reviews
    4. Fill missing optional columns with sensible defaults
    5. Normalize category labels
    6. Preserve natural language text for BERT

    Raises ValueError if required columns are missing.
    """
    missing = validate_columns(df)
    if missing:
        raise ValueError(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Required columns are: {', '.join(REQUIRED_COLUMNS)}"
        )

    df = df.copy()

    # --- Remove empty reviews ---
    df["review_text"] = df["review_text"].astype(str).str.strip()
    df = df[df["review_text"] != ""]
    df = df[df["review_text"].str.lower() != "nan"]

    # --- Remove duplicates ---
    df = df.drop_duplicates(subset=["review_text"], keep="first")

    # --- Normalize category ---
    df["category"] = df["category"].apply(normalize_category)

    # --- Ensure optional columns exist with defaults ---
    if "review_id" not in df.columns:
        df["review_id"] = range(1, len(df) + 1)

    if "product_name" not in df.columns:
        df["product_name"] = "Unknown"
    else:
        df["product_name"] = df["product_name"].fillna("Unknown")

    if "rating" not in df.columns:
        df["rating"] = None  # optional numeric field
    if "platform" not in df.columns:
        df["platform"] = None
    else:
        df["platform"] = df["platform"].fillna(None)

    if "country" not in df.columns:
        df["country"] = None
    else:
        df["country"] = df["country"].fillna(None)

    if "review_date" not in df.columns:
        df["review_date"] = None
    else:
        df["review_date"] = df["review_date"].fillna(None)

    # Reset index after filtering
    df = df.reset_index(drop=True)

    return df


def get_missing_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return a summary of missing values per column for display."""
    summary = df.isnull().sum().reset_index()
    summary.columns = ["Column", "Missing Count"]
    summary["Total Rows"] = len(df)
    summary["Missing %"] = (summary["Missing Count"] / len(df) * 100).round(1)
    return summary


def get_category_counts(df: pd.DataFrame) -> dict[str, int]:
    """Return counts of reviews per category."""
    counts = df["category"].value_counts().to_dict()
    return {"Phone": counts.get("Phone", 0), "Laptop": counts.get("Laptop", 0)}