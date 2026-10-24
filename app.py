"""RefurbIQ — Refurbished Product Review Intelligence.

Streamlit entry point. All ML logic lives in src/; this file only
handles UI layout, user input, and visualization.

Run with:  streamlit run app.py
"""

import inspect
import os

import pandas as pd
import plotly.express as px
import streamlit as st

from src.absa import ABSAEngine
from src.analytics import (
    SENTIMENT_ORDER,
    calculate_statistics,
    generate_insights,
    get_available_products,
    get_platforms_for_product,
    sentiment_by_column,
)
from src.preprocessing import (
    REQUIRED_COLUMNS,
    clean_reviews,
    get_category_counts,
    get_missing_summary,
    load_data,
)
from src.recommendation import (
    ASPECT_GROUPS,
    BEST_FOR_FILTERS,
    DEFAULT_WEIGHTS,
    MIN_REVIEWS_THRESHOLD,
    WEIGHT_LABELS,
    buying_recommendation,
    compute_platform_scores,
    explain_recommendation,
    get_best_for_filter,
    rank_platforms,
    seller_breakdown,
)

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV_PATH = os.path.join(BASE_DIR, "data", "raw", "reviews.csv")
RESULTS_PATH = os.path.join(BASE_DIR, "data", "processed", "absa_results.csv")

SENTIMENT_COLORS = {
    "Positive": "#22c55e",
    "Neutral": "#eab308",
    "Negative": "#ef4444",
}
SENTIMENT_ICONS = {"Positive": "🟢", "Neutral": "🟡", "Negative": "🔴"}

# Recommendation score factors in display order.
SCORE_FACTORS = list(WEIGHT_LABELS)

CONFIDENCE_BADGES = {
    "HIGH": "🟢 HIGH confidence",
    "MEDIUM": "🟡 MEDIUM confidence",
    "LOW": "🔴 LOW confidence",
}


def _width_kw(element) -> dict:
    """Full-width kwargs that work across Streamlit versions."""
    params = inspect.signature(element).parameters
    if "width" in params:
        return {"width": "stretch"}
    if "use_container_width" in params:
        return {"use_container_width": True}
    return {}


st.set_page_config(page_title="RefurbIQ", page_icon="🔍", layout="wide")

# Light visual polish matching the website frontend / presentation palette
# (navy #1F3864, teal #1F6F78, crimson #B03A5B). Presentation only — no
# analysis logic is affected. The Streamlit menu and footer stay as-is; the
# embedded view (?embed=true) already hides them.
st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; }
      h1, h2, h3 {
        font-family: Georgia, Cambria, "Times New Roman", Times, serif;
        color: #1F3864;
      }
      div[data-testid="stMetric"] {
        background: #FFFFFF;
        border-radius: 0.75rem;
        padding: 0.9rem 1.1rem;
        box-shadow: 0 4px 16px rgba(31, 56, 100, 0.08);
      }
      div[data-testid="stMetric"] label { color: #26323F; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- Model & pipeline helpers (ML logic itself stays in src/) ---
@st.cache_resource(show_spinner="Loading sentiment model…")
def get_engine() -> ABSAEngine:
    """Cached BERT engine shared across reruns."""
    return ABSAEngine()


def analyze_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Run ABSA over a cleaned DataFrame with a friendly failure mode."""
    engine = get_engine()
    if not engine.is_available:
        st.error(
            "The sentiment model could not be loaded, so reviews cannot be "
            f"analyzed right now.\n\nDetails: {engine.load_error}"
        )
        st.stop()
    with st.spinner("Analyzing reviews…"):
        return engine.run_absa(df)


def initial_results() -> pd.DataFrame:
    """Reuse processed results if present, else analyze the bundled sample."""
    if os.path.exists(RESULTS_PATH):
        return pd.read_csv(RESULTS_PATH)
    df = clean_reviews(load_data(DEFAULT_CSV_PATH))
    results = analyze_dataframe(df)
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    results.to_csv(RESULTS_PATH, index=False)
    return results


def show_chart(fig) -> None:
    st.plotly_chart(fig, **_width_kw(st.plotly_chart))


def grouped_bar(pivot: pd.DataFrame, x_col: str) -> None:
    """Render a grouped Positive/Neutral/Negative bar chart from a pivot."""
    fig = px.bar(
        pivot.reset_index(),
        x=x_col,
        y=SENTIMENT_ORDER,
        color_discrete_map=SENTIMENT_COLORS,
        barmode="group",
    )
    fig.update_layout(height=380, margin=dict(t=20))
    show_chart(fig)


def product_selector(key_prefix: str):
    """Cascading Category → Brand → Model selectors driven by analyzed data.

    Returns the selected product name, or None when nothing is usable.
    """
    catalog = get_available_products(st.session_state.results)
    if not catalog:
        st.info("No analyzed reviews yet — upload a CSV or analyze the sample data first.")
        return None

    col1, col2, col3 = st.columns(3)
    categories = list(catalog)
    with col1:
        category = st.selectbox("Category", categories, key=f"{key_prefix}_cat")
    brands = list(catalog.get(category, {}))
    with col2:
        brand = st.selectbox("Brand", brands or ["—"], key=f"{key_prefix}_brand")
    models = catalog.get(category, {}).get(brand, [])
    with col3:
        product = st.selectbox(
            "Product / Model", models or ["—"], key=f"{key_prefix}_model"
        )
    return product if product != "—" else None


def clear_product_selectors() -> None:
    """Drop cached selector values after a new dataset is analyzed."""
    for k in list(st.session_state):
        if k.endswith(("_cat", "_brand", "_model")):
            del st.session_state[k]


# --- Header ---
st.title("RefurbIQ")
st.subheader("Refurbished Product Review Intelligence")

st.info(
    "Recommendations are based on analyzed review evidence and are not "
    "guarantees of product quality. The bundled dataset is historical "
    "sample data, not live marketplace information."
)

if "results" not in st.session_state:
    st.session_state.results = initial_results()

# Configurable recommendation parameters (edited in the Methodology tab).
if "weights" not in st.session_state:
    st.session_state.weights = dict(DEFAULT_WEIGHTS)
if "min_reviews" not in st.session_state:
    st.session_state.min_reviews = MIN_REVIEWS_THRESHOLD

(
    overview_tab,
    upload_tab,
    analyzer_tab,
    dashboard_tab,
    compare_tab,
    bestbuy_tab,
    explain_tab,
    methodology_tab,
) = st.tabs(
    [
        "Overview",
        "Upload Reviews",
        "Review Analyzer",
        "Analytics Dashboard",
        "Compare Platforms",
        "Best Place to Buy",
        "Explain Recommendation",
        "Methodology",
    ]
)

# --- A. Overview ---
with overview_tab:
    results_df = st.session_state.results
    stats = calculate_statistics(results_df)

    if stats["total_reviews"] == 0:
        st.info("No reviews analyzed yet. Upload a CSV or analyze a review below.")
    else:
        pct = stats["sentiment_percentages"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Reviews analyzed", f"{stats['total_reviews']:,}")
        c2.metric("Positive", f"{pct.get('Positive', 0.0)}%")
        c3.metric("Neutral", f"{pct.get('Neutral', 0.0)}%")
        c4.metric("Negative", f"{pct.get('Negative', 0.0)}%")

        c5, c6 = st.columns(2)
        c5.metric("Most discussed aspect", stats["most_discussed_aspect"] or "—")
        c6.metric("Most negative aspect", stats["most_negative_aspect"] or "—")

# --- B. Upload Reviews ---
with upload_tab:
    uploaded = st.file_uploader("Upload a reviews CSV", type=["csv"])

    if uploaded is not None:
        try:
            raw_df = load_data(uploaded)
            missing = [c for c in REQUIRED_COLUMNS if c not in raw_df.columns]
            if missing:
                st.error(f"Missing required column(s): {', '.join(missing)}")
            else:
                cleaned = clean_reviews(raw_df)
                counts = get_category_counts(cleaned)

                st.write(f"**File name:** {uploaded.name}")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Reviews", len(cleaned))
                c2.metric("Phones", counts.get("Phone", 0))
                c3.metric("Laptops", counts.get("Laptop", 0))
                c4.metric("Cameras", counts.get("Camera", 0))

                st.write("**Missing-value summary**")
                st.dataframe(
                    get_missing_summary(cleaned),
                    hide_index=True,
                    **_width_kw(st.dataframe),
                )

                if st.button("Analyze Reviews", type="primary"):
                    results = analyze_dataframe(cleaned)
                    st.session_state.results = results
                    clear_product_selectors()
                    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
                    results.to_csv(RESULTS_PATH, index=False)
                    st.success(f"Analyzed {len(results)} review–aspect pairs.")
        except Exception as exc:
            st.error(f"Could not read that file: {exc}")
    else:
        st.info(
            "Upload a CSV with at least `review_text` and `category` columns. "
            "A sample file ships in `data/raw/reviews.csv`."
        )

# --- C. Review Analyzer ---
with analyzer_tab:
    review_text = st.text_area(
        "Paste a single review",
        value="The laptop looks almost new but the battery drains very quickly.",
        height=100,
    )
    if st.button("Analyze", type="primary"):
        engine = get_engine()
        if not engine.is_available:
            st.error(
                f"The sentiment model could not be loaded.\n\nDetails: {engine.load_error}"
            )
        elif not review_text.strip():
            st.warning("Please enter a review first.")
        else:
            with st.spinner("Analyzing review…"):
                try:
                    aspect_results = engine.analyze_review(review_text)
                    overall, overall_conf = engine.overall_sentiment(review_text)
                except Exception as exc:
                    st.error(f"Analysis failed: {exc}")
                    aspect_results = []

            if aspect_results:
                st.metric(
                    "Overall sentiment",
                    f"{SENTIMENT_ICONS[overall]} {overall}",
                    help=f"Confidence {overall_conf:.0%}",
                )
                table = pd.DataFrame(aspect_results)
                table["Sentiment"] = table["sentiment"].map(
                    lambda s: f"{SENTIMENT_ICONS[s]} {s}"
                )
                table["Confidence"] = (
                    (table["confidence"] * 100).round(0).astype(int).astype(str) + "%"
                )
                table = table[["aspect", "Sentiment", "Confidence"]].rename(
                    columns={"aspect": "Aspect"}
                )
                st.table(table, **_width_kw(st.table))
            else:
                st.info("No known product aspect was detected in that review.")

# --- D. Analytics Dashboard ---
with dashboard_tab:
    results_df = st.session_state.results
    stats = calculate_statistics(results_df)

    if stats["total_reviews"] == 0:
        st.info("Analyze some reviews to see the dashboard.")
    else:
        st.subheader("Sentiment Distribution")
        dist = (
            pd.Series(stats["sentiment_counts"])
            .reindex(SENTIMENT_ORDER)
            .fillna(0)
        )
        fig_pie = px.pie(
            names=dist.index.tolist(),
            values=dist.values,
            color=dist.index.tolist(),
            color_discrete_map=SENTIMENT_COLORS,
            hole=0.45,
        )
        fig_pie.update_layout(height=380, margin=dict(t=20))
        show_chart(fig_pie)

        st.subheader("Most Discussed Aspects")
        freq = pd.Series(stats["aspect_frequency"]).sort_values()
        fig_freq = px.bar(x=freq.values, y=freq.index, orientation="h")
        fig_freq.update_layout(
            height=400, margin=dict(t=20), xaxis_title="Mentions", yaxis_title=""
        )
        show_chart(fig_freq)

        st.subheader("Sentiment by Aspect")
        pivot = sentiment_by_column(results_df, "aspect")
        if pivot is not None:
            grouped_bar(pivot, "aspect")

        st.subheader("Sentiment by Category")
        pivot = sentiment_by_column(results_df, "category")
        if pivot is not None:
            grouped_bar(pivot, "category")

        if results_df.get("platform") is not None and results_df["platform"].notna().any():
            st.subheader("Sentiment by Platform")
            pivot = sentiment_by_column(results_df, "platform")
            if pivot is not None:
                grouped_bar(pivot, "platform")

        if results_df.get("country") is not None and results_df["country"].notna().any():
            st.subheader("Sentiment by Country")
            pivot = sentiment_by_column(results_df, "country")
            if pivot is not None:
                grouped_bar(pivot, "country")

        st.divider()
        st.subheader("Key Insights")
        for insight in generate_insights(results_df, stats):
            st.write(f"• {insight}")

# --- E. Compare Platforms ---
with compare_tab:
    st.subheader("Compare Platforms")
    product = product_selector("compare")

    if product:
        platforms = get_platforms_for_product(st.session_state.results, product)
        if platforms:
            st.write(
                "Available platforms for this product: "
                + ", ".join(
                    f"{p['platform']} ({p['reviews']} reviews)" for p in platforms
                )
            )

        scores_df = compute_platform_scores(
            st.session_state.results, product, st.session_state.weights
        )

        if scores_df.empty:
            st.warning("No analyzed reviews found for this product.")
        else:
            table = scores_df.rename(
                columns={
                    "platform": "Platform",
                    "reviews": "Reviews",
                    "positive_pct": "Positive %",
                    "neutral_pct": "Neutral %",
                    "negative_pct": "Negative %",
                    "overall": "Score /10",
                    "confidence": "Confidence",
                }
            )[
                [
                    "Platform",
                    "Reviews",
                    "Positive %",
                    "Neutral %",
                    "Negative %",
                    "Score /10",
                    "Confidence",
                ]
            ]
            st.dataframe(table, hide_index=True, **_width_kw(st.dataframe))

            below = scores_df[scores_df["reviews"] < st.session_state.min_reviews]
            if not below.empty:
                st.caption(
                    "⚠️ " + ", ".join(below["platform"]) + " shown for reference "
                    f"but excluded from rankings — fewer than "
                    f"{st.session_state.min_reviews} unique reviews."
                )

            # Radar chart of sub-scores per platform.
            radar_df = scores_df.melt(
                id_vars="platform",
                value_vars=SCORE_FACTORS,
                var_name="factor",
                value_name="score",
            )
            radar_df["factor"] = radar_df["factor"].map(WEIGHT_LABELS)
            fig = px.line_polar(
                radar_df,
                r="score",
                theta="factor",
                color="platform",
                line_close=True,
                range_r=[0, 10],
            )
            fig.update_traces(fill="toself")
            fig.update_layout(height=450, margin=dict(t=30))
            show_chart(fig)

            # "Best for X" quick rankings.
            st.subheader("Best for…")
            cols = st.columns(4)
            for i, (label, aspects) in enumerate(BEST_FOR_FILTERS):
                best = get_best_for_filter(
                    st.session_state.results,
                    aspects,
                    product,
                    st.session_state.min_reviews,
                )
                with cols[i % len(cols)]:
                    if best:
                        st.metric(
                            label,
                            best["platform"],
                            help=(
                                f"{best['score']:.1f}/10 from "
                                f"{best['reviews']} reviews"
                            ),
                        )
                    else:
                        st.metric(label, "Insufficient data")

            # Seller-level sentiment, only where seller data exists.
            sellers = seller_breakdown(st.session_state.results, product)
            if sellers is not None and not sellers.empty:
                with st.expander("Seller-level sentiment (where available)"):
                    st.caption(
                        "Shown only where individual seller information exists. "
                        "Seller quality is never inferred from platform-level "
                        "sentiment."
                    )
                    st.dataframe(sellers, hide_index=True, **_width_kw(st.dataframe))

# --- F. Best Place to Buy ---
with bestbuy_tab:
    st.subheader("Best Place to Buy")
    product = product_selector("bestbuy")

    if product:
        rec = buying_recommendation(
            st.session_state.results,
            product,
            st.session_state.weights,
            st.session_state.min_reviews,
        )

        st.write(f"**Reviews analyzed:** {rec['reviews_analyzed']}")
        st.caption("Recommendation based on available historical review data.")

        if rec["recommended"] is None:
            st.warning(
                "The data is insufficient to recommend a platform for this "
                "product. " + " ".join(rec["warnings"])
            )
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Recommended platform", f"🥇 {rec['recommended']}")
            c2.metric("Recommendation score", f"{rec['overall']:.1f} / 10")
            c3.metric("Confidence", CONFIDENCE_BADGES[rec["confidence"]])
            if rec["runner_up"]:
                st.caption(f"Runner-up: {rec['runner_up']}")

            st.markdown("**Why?**")
            for reason in rec["why"]:
                st.write(f"• {reason}")

            st.markdown("**⚠️ Things to check before purchasing**")
            if rec["warnings"]:
                for warning in rec["warnings"]:
                    st.write(f"• {warning}")
            else:
                st.write("• No major red flags found in the analyzed reviews.")

# --- G. Explain Recommendation ---
with explain_tab:
    st.subheader("Explain Recommendation")
    product = product_selector("explain")

    if product:
        ranked = rank_platforms(
            st.session_state.results,
            product,
            st.session_state.weights,
            st.session_state.min_reviews,
        )
        explanation = explain_recommendation(
            ranked,
            st.session_state.results,
            product,
            st.session_state.min_reviews,
        )
        st.info(explanation)

        scores_df = compute_platform_scores(
            st.session_state.results, product, st.session_state.weights
        )
        if not scores_df.empty:
            st.markdown("#### Factor-by-factor breakdown")
            breakdown = scores_df.set_index("platform")[SCORE_FACTORS].copy()
            breakdown = breakdown.rename(columns=WEIGHT_LABELS).T
            st.dataframe(
                breakdown.style.highlight_max(axis=1, color="#dcfce7"),
                **_width_kw(st.dataframe),
            )
            st.caption(
                "Scores are 0–10. Green highlights the best platform for "
                "each factor. Platforms below the minimum review threshold "
                "are shown but not ranked."
            )

# --- H. Methodology ---
with methodology_tab:
    st.subheader("Methodology")

    st.markdown("#### How the recommendation score works")
    st.markdown(
        "Each sub-score is **0–10**, computed from the sentiment distribution "
        "of the analyzed aspect mentions:\n\n"
        "`sub-score = (Positive% × 1.0 + Neutral% × 0.5 + Negative% × 0.0) / 10`\n\n"
        "The **Overall Recommendation Score** is the weighted sum:"
    )
    formula = " + ".join(WEIGHT_LABELS.values())
    st.code(f"Overall = {formula}", language=None)

    st.markdown("#### Configure weights")
    st.caption(
        "Weights are re-normalised automatically, so they don't need to sum to 1. "
        "Changes apply to every recommendation tab immediately."
    )
    for key, label in WEIGHT_LABELS.items():
        st.session_state.weights[key] = st.slider(
            label,
            0.0,
            0.5,
            float(st.session_state.weights[key]),
            0.05,
            key=f"weight_{key}",
        )
    st.caption(f"Current weight sum: {sum(st.session_state.weights.values()):.2f}")

    st.markdown("#### Minimum review threshold")
    st.session_state.min_reviews = st.slider(
        "Platforms with fewer unique reviews than this are excluded from rankings",
        5,
        100,
        st.session_state.min_reviews,
        5,
        key="min_reviews_slider",
    )

    st.markdown("#### Confidence levels")
    st.markdown(
        "- **HIGH** — at least 50 reviews and consistent sentiment\n"
        "- **MEDIUM** — at least the minimum threshold of reviews\n"
        "- **LOW** — below the threshold; no recommendation is made"
    )

    st.markdown("#### Score components")
    for factor, label in WEIGHT_LABELS.items():
        if factor == "sentiment":
            source = "all analyzed aspect mentions"
        else:
            source = ", ".join(ASPECT_GROUPS[factor])
        st.write(f"- **{label}** — sentiment over: {source}")

    st.divider()
    st.caption(
        "This tool analyzes review evidence only. It does not verify current "
        "prices, availability, warranties or real-time seller performance. "
        "A recommendation is evidence about past buyer sentiment, not a "
        "guarantee of product quality."
    )