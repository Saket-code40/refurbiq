"""Recommendation engine for RefurbIQ.

Consumes validated ABSA results (one row per review–aspect pair) and
produces transparent, multi-factor platform recommendation scores.

Scoring methodology:
  Each sub-score is 0–10, computed from the sentiment distribution of
  the relevant aspect group:

      score = (positive% * 1.0 + neutral% * 0.5 + negative% * 0.0) * 10

  Overall Recommendation Score = weighted sum of sub-scores using
  DEFAULT_WEIGHTS (configurable at runtime).

  Platforms with fewer than MIN_REVIEWS_THRESHOLD unique reviews are
  excluded from ranking and flagged as "insufficient data" — the app
  must never claim a winner on a tiny sample.

The engine is deliberately separate from the ML layer: it only reads
the validated aspect/sentiment results, never raw model confidences.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

# Minimum unique reviews before a platform can be ranked.
MIN_REVIEWS_THRESHOLD = 20

# Default weights for the overall recommendation score (must sum to 1).
DEFAULT_WEIGHTS: dict[str, float] = {
    "sentiment": 0.25,
    "product_quality": 0.25,
    "service": 0.15,
    "value": 0.15,
    "trust": 0.10,
    "return_refund": 0.10,
}

# Human-readable names for each score component.
WEIGHT_LABELS: dict[str, str] = {
    "sentiment": "Overall Sentiment",
    "product_quality": "Product Quality",
    "service": "Service (Delivery/Packaging/Support)",
    "value": "Value for Money",
    "trust": "Trust & Refurbishment Quality",
    "return_refund": "Return/Refund Experience",
}

# Which aspects feed each sub-score.
ASPECT_GROUPS: dict[str, list[str]] = {
    "product_quality": ["Condition", "Battery", "Performance", "Display", "Camera"],
    "service": ["Seller Service", "Delivery", "Packaging"],
    "value": ["Price/Value"],
    "trust": ["Trust/Authenticity", "Repair/Refurbishment"],
    "return_refund": ["Return/Refund"],
}

# Named comparison filters for the "Best for X" rankings.
BEST_FOR_FILTERS: list[tuple[str, Optional[list[str]]]] = [
    ("Best Overall", None),
    ("Best Product Condition", ["Condition"]),
    ("Best Battery Experience", ["Battery"]),
    ("Best Performance", ["Performance"]),
    ("Best Value for Money", ["Price/Value"]),
    ("Best Customer Service", ["Seller Service"]),
    ("Best Return Experience", ["Return/Refund"]),
    ("Most Trusted", ["Trust/Authenticity"]),
]

NUMERIC_SENTIMENT = {"Positive": 1.0, "Neutral": 0.5, "Negative": 0.0}

SENTIMENT_ORDER = ["Positive", "Neutral", "Negative"]


# --- helpers -----------------------------------------------------------------

def _product_frame(
    results_df: pd.DataFrame, product_name: Optional[str] = None
) -> pd.DataFrame:
    """Filter results to a single product (or return everything)."""
    if product_name is None or results_df.empty:
        return results_df
    return results_df[results_df["product_name"] == product_name]


def unique_review_count(df: pd.DataFrame) -> int:
    """Count unique reviews (by review_id when available)."""
    if df.empty:
        return 0
    if "review_id" in df.columns and df["review_id"].notna().any():
        return int(df["review_id"].nunique())
    return len(df)


def sentiment_distribution(sentiment: pd.Series) -> dict[str, float]:
    """Return Positive/Neutral/Negative percentages (0–100)."""
    dist = {s: 0.0 for s in SENTIMENT_ORDER}
    counts = sentiment.value_counts()
    total = float(counts.sum()) if len(counts) else 0.0
    if total == 0:
        return dist
    for s in SENTIMENT_ORDER:
        dist[s] = round(float(counts.get(s, 0)) / total * 100, 1)
    return dist


def compute_sentiment_score(sentiment: pd.Series) -> float:
    """Score a sentiment series on 0–10.

    Positive counts fully, Neutral half, Negative zero.
    """
    if sentiment.empty:
        return 0.0
    values = sentiment.map(NUMERIC_SENTIMENT).dropna()
    if values.empty:
        return 0.0
    return round(float(values.mean()) * 10, 2)


def compute_aspect_group_score(
    results_df: pd.DataFrame, aspects: list[str]
) -> Optional[float]:
    """Score the rows whose aspect is in `aspects`.

    Returns None when no rows match (caller decides the fallback), so
    missing data is never silently invented.
    """
    subset = results_df[results_df["aspect"].isin(aspects)]
    if subset.empty:
        return None
    return compute_sentiment_score(subset["sentiment"])


def compute_confidence(n_reviews: int, sentiment: pd.Series) -> str:
    """Confidence level based on sample size and sentiment consistency.

    HIGH   — >= 50 reviews and consistent sentiment (low spread)
    MEDIUM — >= MIN_REVIEWS_THRESHOLD reviews
    LOW    — below the threshold; no recommendation should be made
    """
    if n_reviews < MIN_REVIEWS_THRESHOLD:
        return "LOW"
    numeric = sentiment.map(NUMERIC_SENTIMENT).dropna()
    std = float(numeric.std()) if len(numeric) > 1 else 0.0
    if n_reviews >= 50 and std <= 0.35:
        return "HIGH"
    return "MEDIUM"


# --- platform scoring ---------------------------------------------------------

def compute_platform_scores(
    results_df: pd.DataFrame,
    product_name: Optional[str] = None,
    weights: Optional[dict[str, float]] = None,
) -> pd.DataFrame:
    """Compute per-platform sub-scores and overall recommendation score.

    Returns a DataFrame with columns:
        platform, reviews, positive_pct, neutral_pct, negative_pct,
        sentiment, product_quality, service, value, trust,
        return_refund, overall, confidence, missing_factors
    """
    weights = weights or DEFAULT_WEIGHTS
    df = _product_frame(results_df, product_name)

    rows = []
    if df.empty or "platform" not in df.columns:
        return pd.DataFrame(rows)

    for platform, plat_df in df.groupby("platform"):
        n_reviews = unique_review_count(plat_df)
        dist = sentiment_distribution(plat_df["sentiment"])

        # Overall sentiment sub-score across all aspect rows.
        scores: dict[str, Optional[float]] = {
            "sentiment": compute_sentiment_score(plat_df["sentiment"])
        }

        # Aspect-group sub-scores; fall back to the overall sentiment
        # score when a group has no rows, but record the gap.
        missing_factors: list[str] = []
        for factor, aspects in ASPECT_GROUPS.items():
            group_score = compute_aspect_group_score(plat_df, aspects)
            if group_score is None:
                group_score = scores["sentiment"]
                missing_factors.append(WEIGHT_LABELS[factor])
            scores[factor] = group_score

        # Weighted overall score (weights are re-normalised defensively).
        total_w = sum(weights.get(k, 0.0) for k in scores)
        if total_w > 0:
            overall = sum(
                scores[k] * weights.get(k, 0.0) / total_w for k in scores
            )
        else:
            overall = scores["sentiment"]

        rows.append(
            {
                "platform": platform,
                "reviews": n_reviews,
                "positive_pct": dist["Positive"],
                "neutral_pct": dist["Neutral"],
                "negative_pct": dist["Negative"],
                **{k: round(v, 2) for k, v in scores.items()},
                "overall": round(overall, 2),
                "confidence": compute_confidence(n_reviews, plat_df["sentiment"]),
                "missing_factors": missing_factors,
            }
        )

    return pd.DataFrame(rows).sort_values("overall", ascending=False).reset_index(drop=True)


def rank_platforms(
    results_df: pd.DataFrame,
    product_name: Optional[str] = None,
    weights: Optional[dict[str, float]] = None,
    min_reviews: int = MIN_REVIEWS_THRESHOLD,
) -> list[dict]:
    """Ranked platforms that meet the minimum review threshold.

    Each entry is a dict with platform, overall score, reviews and
    confidence. Platforms below the threshold are excluded entirely.
    """
    scores_df = compute_platform_scores(results_df, product_name, weights)
    if scores_df.empty:
        return []
    eligible = scores_df[scores_df["reviews"] >= min_reviews]
    return eligible.to_dict(orient="records")


# --- explanations -------------------------------------------------------------

def explain_recommendation(
    ranked: list[dict],
    results_df: pd.DataFrame,
    product_name: Optional[str] = None,
    min_reviews: int = MIN_REVIEWS_THRESHOLD,
) -> str:
    """Plain-language explanation of why the top platform ranks first.

    Built strictly from the computed scores — nothing is invented.
    """
    if not ranked:
        return (
            "No platform has enough reviews to rank for this selection. "
            f"At least {min_reviews} unique reviews per platform are required."
        )

    top = ranked[0]
    product_txt = f" for {product_name}" if product_name else ""
    parts = [
        f"{top['platform']} is ranked #1{product_txt} with an overall score of "
        f"{top['overall']:.1f}/10 based on {top['reviews']} reviews "
        f"({top['confidence'].lower()} confidence)."
    ]

    # Compare against the runner-up factor by factor.
    if len(ranked) >= 2:
        second = ranked[1]
        advantages = []
        for factor in ["sentiment", *ASPECT_GROUPS]:
            gap = float(top[factor]) - float(second[factor])
            if gap >= 0.5:
                advantages.append((WEIGHT_LABELS[factor], gap))
        advantages.sort(key=lambda x: -x[1])
        if advantages:
            names = " and ".join(
                f"{name} (+{gap:.1f})" for name, gap in advantages[:3]
            )
            parts.append(
                f"It leads {second['platform']} mainly on {names}."
            )
        else:
            parts.append(
                f"It edges out {second['platform']} by a small margin "
                f"({top['overall']:.1f} vs {second['overall']:.1f}) across all factors."
            )

    # Note the leader's weak spots so the explanation stays balanced.
    weak = [
        WEIGHT_LABELS[f]
        for f in ["sentiment", *ASPECT_GROUPS]
        if float(top[f]) <= 5.0
    ]
    if weak:
        parts.append(
            "However, note weaker areas: " + ", ".join(weak) + "."
        )

    return " ".join(parts)


# --- "best for X" filters ------------------------------------------------------

def get_best_for_filter(
    results_df: pd.DataFrame,
    aspects: Optional[list[str]],
    product_name: Optional[str] = None,
    min_reviews: int = MIN_REVIEWS_THRESHOLD,
) -> Optional[dict]:
    """Best platform for a named filter (None aspects = overall score).

    Returns {"platform", "score", "reviews"} or None when no platform
    has enough data — callers must not display a winner in that case.
    """
    df = _product_frame(results_df, product_name)
    if df.empty or "platform" not in df.columns:
        return None

    best = None
    for platform, plat_df in df.groupby("platform"):
        n_reviews = unique_review_count(plat_df)
        if n_reviews < min_reviews:
            continue
        if aspects is None:
            score = compute_sentiment_score(plat_df["sentiment"])
        else:
            score = compute_aspect_group_score(plat_df, aspects)
            if score is None:
                continue
        if best is None or score > best["score"]:
            best = {"platform": platform, "score": score, "reviews": n_reviews}
    return best


# --- buying recommendation ------------------------------------------------------

def buying_recommendation(
    results_df: pd.DataFrame,
    product_name: Optional[str] = None,
    weights: Optional[dict[str, float]] = None,
    min_reviews: int = MIN_REVIEWS_THRESHOLD,
) -> dict:
    """Full buying recommendation for a product.

    Returns a dict with:
        recommended (str | None), overall, confidence, reviews_analyzed,
        why (list[str]), warnings (list[str]), runner_up (str | None)
    When data is insufficient `recommended` is None and the UI must
    refuse to recommend.
    """
    ranked = rank_platforms(results_df, product_name, weights, min_reviews)
    df = _product_frame(results_df, product_name)
    total_reviews = unique_review_count(df)

    result = {
        "recommended": None,
        "overall": None,
        "confidence": "LOW",
        "reviews_analyzed": total_reviews,
        "why": [],
        "warnings": [],
        "runner_up": None,
    }

    if not ranked:
        result["warnings"].append(
            f"No platform has at least {min_reviews} unique reviews for this "
            "selection, so no recommendation can be made."
        )
        return result

    top = ranked[0]
    result["recommended"] = top["platform"]
    result["overall"] = top["overall"]
    result["confidence"] = top["confidence"]
    if len(ranked) > 1:
        result["runner_up"] = ranked[1]["platform"]

    # Positive factors: sub-scores of 7+ on the winning platform.
    for factor in ["sentiment", *ASPECT_GROUPS]:
        if float(top[factor]) >= 7.0:
            result["why"].append(
                f"Strong {WEIGHT_LABELS[factor].lower()}: "
                f"{top[factor]:.1f}/10"
            )
    if not result["why"]:
        result["why"].append(
            f"Highest overall score ({top['overall']:.1f}/10) among platforms "
            "with sufficient review volume."
        )

    # Warning factors: sub-scores of 5 or below, or high negative share.
    for factor in ["sentiment", *ASPECT_GROUPS]:
        if float(top[factor]) <= 5.0:
            result["warnings"].append(
                f"Weaker {WEIGHT_LABELS[factor].lower()} "
                f"({top[factor]:.1f}/10) — check recent reviews."
            )
    if float(top["negative_pct"]) >= 25.0:
        result["warnings"].append(
            f"{top['negative_pct']:.0f}% of analyzed mentions are negative."
        )

    return result


# --- seller-level view -----------------------------------------------------------

def seller_breakdown(
    results_df: pd.DataFrame,
    product_name: Optional[str] = None,
    platform: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    """Per-seller sentiment where seller data actually exists.

    Returns None when no seller column or no usable rows, so platform
    sentiment is never mis-presented as seller sentiment.
    """
    df = _product_frame(results_df, product_name)
    if df.empty or "seller" not in df.columns:
        return None
    if platform is not None:
        df = df[df["platform"] == platform]
    df = df[df["seller"].notna() & (df["seller"] != "Unknown")]
    if df.empty:
        return None

    rows = []
    for seller, seller_df in df.groupby("seller"):
        dist = sentiment_distribution(seller_df["sentiment"])
        rows.append(
            {
                "seller": seller,
                "platform": seller_df["platform"].mode().iloc[0],
                "reviews": unique_review_count(seller_df),
                "positive_pct": dist["Positive"],
                "neutral_pct": dist["Neutral"],
                "negative_pct": dist["Negative"],
                "score": compute_sentiment_score(seller_df["sentiment"]),
            }
        )
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)