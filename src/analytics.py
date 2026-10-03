"""Analytics layer for RefurbIQ.

Takes ABSA result rows (one row per review-aspect pair) and computes
aggregate statistics and automated insights. All insights are derived
from the actual data — nothing is hardcoded.
"""

import pandas as pd

SENTIMENT_ORDER = ["Positive", "Neutral", "Negative"]


def calculate_statistics(results_df: pd.DataFrame) -> dict:
    """Compute high-level statistics from ABSA results.

    Args:
        results_df: DataFrame with columns including
                    review_id, aspect, sentiment.

    Returns:
        dict with keys: total_reviews, sentiment_counts,
        sentiment_percentages, aspect_frequency, most_discussed_aspect,
        most_negative_aspect, aspect_sentiment_breakdown.
    """
    if results_df.empty:
        return {
            "total_reviews": 0,
            "sentiment_counts": {},
            "sentiment_percentages": {},
            "aspect_frequency": {},
            "most_discussed_aspect": None,
            "most_negative_aspect": None,
            "aspect_sentiment_breakdown": {},
        }

    # Unique reviews analyzed
    total_reviews = results_df["review_id"].nunique()

    # Overall sentiment distribution (across all aspect mentions)
    sentiment_counts = results_df["sentiment"].value_counts().to_dict()
    total_mentions = len(results_df)
    sentiment_percentages = {
        label: round(count / total_mentions * 100, 1)
        for label, count in sentiment_counts.items()
    }

    # Aspect frequency
    aspect_frequency = results_df["aspect"].value_counts().to_dict()
    most_discussed_aspect = (
        results_df["aspect"].value_counts().index[0]
        if not results_df["aspect"].empty
        else None
    )

    # Aspect-level sentiment breakdown (percentages per aspect)
    breakdown = {}
    for aspect in results_df["aspect"].unique():
        subset = results_df[results_df["aspect"] == aspect]
        counts = subset["sentiment"].value_counts()
        n = len(subset)
        breakdown[aspect] = {
            label: round(counts.get(label, 0) / n * 100, 1)
            for label in SENTIMENT_ORDER
        }

    # Most negative aspect = highest proportion of Negative sentiment
    # (only among aspects mentioned at least twice to avoid noise)
    most_negative_aspect = None
    highest_neg_pct = -1.0
    for aspect, stats in breakdown.items():
        freq = aspect_frequency.get(aspect, 0)
        if freq >= 2 and stats.get("Negative", 0) > highest_neg_pct:
            highest_neg_pct = stats["Negative"]
            most_negative_aspect = aspect

    return {
        "total_reviews": int(total_reviews),
        "sentiment_counts": sentiment_counts,
        "sentiment_percentages": sentiment_percentages,
        "aspect_frequency": aspect_frequency,
        "most_discussed_aspect": most_discussed_aspect,
        "most_negative_aspect": most_negative_aspect,
        "aspect_sentiment_breakdown": breakdown,
    }


def generate_insights(results_df: pd.DataFrame, stats: dict) -> list[str]:
    """Generate automated insights from computed statistics.

    Every insight is derived from actual data values — no invented
    statistics.

    Returns a list of human-readable insight strings.
    """
    insights: list[str] = []

    if results_df.empty or stats["total_reviews"] == 0:
        return ["No reviews analyzed yet."]

    breakdown = stats["aspect_sentiment_breakdown"]
    aspect_frequency = stats["aspect_frequency"]

    # 1. Most discussed aspect
    most_discussed = stats["most_discussed_aspect"]
    if most_discussed:
        count = aspect_frequency[most_discussed]
        insights.append(
            f"{most_discussed} is the most frequently discussed aspect "
            f"({count} mention{'s' if count != 1 else ''})."
        )

    # 2. Aspect with highest negative proportion
    most_negative = stats["most_negative_aspect"]
    if most_negative and most_negative in breakdown:
        neg_pct = breakdown[most_negative]["Negative"]
        insights.append(
            f"{most_negative} has a relatively high proportion of negative "
            f"sentiment ({neg_pct}%)."
        )

    # 3. Aspects that are predominantly positive
    for aspect, sb in breakdown.items():
        freq = aspect_frequency.get(aspect, 0)
        if freq >= 2 and sb.get("Positive", 0) >= 70:
            insights.append(
                f"{aspect} is predominantly positive "
                f"({sb['Positive']}% positive mentions)."
            )

    # 4. Aspects with comparatively negative sentiment
    # (negative % above the overall average)
    total_mentions = len(results_df)
    overall_neg_pct = (
        results_df["sentiment"].value_counts().get("Negative", 0)
        / total_mentions * 100
        if total_mentions else 0
    )
    for aspect, sb in breakdown.items():
        if aspect == most_negative:
            continue  # already reported above
        freq = aspect_frequency.get(aspect, 0)
        if freq >= 2 and sb.get("Negative", 0) > overall_neg_pct + 10:
            insights.append(
                f"{aspect} sentiment is comparatively negative "
                f"({sb['Negative']}% vs {round(overall_neg_pct, 1)}% overall)."
            )

    # 5. Overall sentiment summary
    pos_pct = stats["sentiment_percentages"].get("Positive", 0)
    neg_pct = stats["sentiment_percentages"].get("Negative", 0)
    insights.append(
        f"Overall, {pos_pct}% of aspect mentions are positive and "
        f"{neg_pct}% are negative."
    )

    return insights


def sentiment_by_column(results_df: pd.DataFrame, column: str) -> pd.DataFrame | None:
    """Return a pivot of sentiment distribution grouped by a column.

    Returns None if the column doesn't exist or has no valid data.
    """
    if column not in results_df.columns:
        return None

    subset = results_df.dropna(subset=[column])
    if subset.empty:
        return None

    pivot = (
        subset.groupby([column, "sentiment"])
        .size()
        .unstack(fill_value=0)
    )
    # Ensure all sentiment columns present
    for label in SENTIMENT_ORDER:
        if label not in pivot.columns:
            pivot[label] = 0
    pivot = pivot[SENTIMENT_ORDER]
    return pivot