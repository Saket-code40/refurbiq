"""Aggregation and insight generation over ABSA results.

Insights are computed strictly from the data — no hard-coded claims.
"""

from __future__ import annotations

import pandas as pd

SENTIMENT_ORDER = ["Positive", "Neutral", "Negative"]


def calculate_statistics(results_df: pd.DataFrame) -> dict:
    """Aggregate counts, percentages, and aspect-level summaries."""
    stats: dict = {
        "total_reviews": 0,
        "sentiment_counts": {s: 0 for s in SENTIMENT_ORDER},
        "sentiment_percentages": {s: 0.0 for s in SENTIMENT_ORDER},
        "aspect_frequency": {},
        "most_discussed_aspect": None,
        "most_negative_aspect": None,
        "negative_rate_by_aspect": {},
    }

    if results_df is None or results_df.empty:
        return stats

    total = len(results_df)
    counts = results_df["sentiment"].value_counts()
    stats["total_reviews"] = int(total)
    stats["sentiment_counts"] = {
        s: int(counts.get(s, 0)) for s in SENTIMENT_ORDER
    }
    stats["sentiment_percentages"] = {
        s: round(100 * counts.get(s, 0) / total, 1) for s in SENTIMENT_ORDER
    }

    aspect_frequency = results_df["aspect"].value_counts()
    stats["aspect_frequency"] = aspect_frequency.to_dict()
    stats["most_discussed_aspect"] = (
        aspect_frequency.index[0] if len(aspect_frequency) else None
    )

    # Negative share per aspect — drives the "most negative aspect" insight.
    negative_rate = (
        results_df.assign(negative=results_df["sentiment"].eq("Negative"))
        .groupby("aspect")["negative"]
        .mean()
    )
    stats["negative_rate_by_aspect"] = negative_rate.round(3).to_dict()
    if len(negative_rate):
        stats["most_negative_aspect"] = negative_rate.idxmax()

    return stats


def sentiment_by_column(results_df: pd.DataFrame, column: str):
    """Pivot of sentiment counts grouped by a column, or None if unusable."""
    if column not in results_df.columns:
        return None
    subset = results_df.dropna(subset=[column])
    if subset.empty:
        return None
    pivot = (
        subset.groupby([column, "sentiment"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=SENTIMENT_ORDER, fill_value=0)
    )
    return pivot


def generate_insights(results_df: pd.DataFrame, stats: dict) -> list[str]:
    """Plain-language insights derived only from the computed statistics."""
    insights: list[str] = []

    if stats["total_reviews"] == 0:
        return ["No reviews analyzed yet."]

    pct = stats["sentiment_percentages"]
    insights.append(
        f"Overall, {pct.get('Positive', 0.0)}% of aspect mentions are positive, "
        f"{pct.get('Neutral', 0.0)}% neutral, and {pct.get('Negative', 0.0)}% negative."
    )

    if stats["most_discussed_aspect"]:
        freq = stats["aspect_frequency"]
        top_aspect = stats["most_discussed_aspect"]
        insights.append(
            f"'{top_aspect}' is the most discussed aspect with "
            f"{freq.get(top_aspect, 0)} mentions."
        )

    if stats["most_negative_aspect"]:
        rates = stats["negative_rate_by_aspect"]
        worst = stats["most_negative_aspect"]
        insights.append(
            f"'{worst}' generates the most negative sentiment — "
            f"{rates.get(worst, 0) * 100:.0f}% of its mentions are negative."
        )

    # Category with the highest negative share, when categories exist.
    if "category" in results_df.columns and results_df["category"].notna().any():
        cat_pivot = sentiment_by_column(results_df, "category")
        if cat_pivot is not None and "Negative" in cat_pivot.columns:
            totals = cat_pivot.sum(axis=1)
            negative_share = (cat_pivot["Negative"] / totals.replace(0, pd.NA)).dropna()
            if len(negative_share):
                worst_cat = negative_share.idxmax()
                insights.append(
                    f"'{worst_cat}' reviews carry the highest negative share "
                    f"({negative_share[worst_cat] * 100:.0f}%)."
                )

    insights.append(
        "Tip: prioritize seller follow-up on the most negative aspect to "
        "improve refurbishment quality perception."
    )
    return insights
