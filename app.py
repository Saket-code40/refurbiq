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
    sentiment_by_column,
)
from src.preprocessing import (
    REQUIRED_COLUMNS,
    clean_reviews,
    get_category_counts,
    get_missing_summary,
    load_data,
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


def _width_kw(element) -> dict:
    """Full-width kwargs that work across Streamlit versions."""
    params = inspect.signature(element).parameters
    if "width" in params:
        return {"width": "stretch"}
    if "use_container_width" in params:
        return {"use_container_width": True}
    return {}


st.set_page_config(page_title="RefurbIQ", page_icon="🔍", layout="wide")


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


# --- Header ---
st.title("RefurbIQ")
st.subheader("Refurbished Product Review Intelligence")

if "results" not in st.session_state:
    st.session_state.results = initial_results()

overview_tab, upload_tab, analyzer_tab, dashboard_tab = st.tabs(
    ["Overview", "Upload Reviews", "Review Analyzer", "Analytics Dashboard"]
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
                c1, c2, c3 = st.columns(3)
                c1.metric("Reviews", len(cleaned))
                c2.metric("Phones", counts.get("Phone", 0))
                c3.metric("Laptops", counts.get("Laptop", 0))

                st.write("**Missing-value summary**")
                st.dataframe(
                    get_missing_summary(cleaned),
                    hide_index=True,
                    **_width_kw(st.dataframe),
                )

                if st.button("Analyze Reviews", type="primary"):
                    results = analyze_dataframe(cleaned)
                    st.session_state.results = results
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