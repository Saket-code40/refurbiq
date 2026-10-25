"""Generate draw.io-style diagrams for the RefurbIQ deck.

Four flat-design PNGs (white background, coloured rounded boxes, chunky
arrows) built with matplotlib so they drop straight into PowerPoint:

  1_diagram_tech_stack.png        layered technology stack
  2_diagram_app_workflow.png      end-to-end app pipeline
  3_diagram_research_pipeline.png research / ML evaluation pipeline
  4_diagram_recommendation.png    recommendation-engine scoring flow

Every label comes from the actual codebase (app tabs, src modules, model
configs); no invented components.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path(__file__).resolve().parent

# Palette loosely matching the example deck style.
NAVY   = "#1F3A5F"
TEAL   = "#2A9D8F"
CORAL  = "#E76F51"
ORANGE = "#F4A261"
PINK   = "#E5989B"
GREEN  = "#588157"
PURPLE = "#7B2CBF"
GREY   = "#6C757D"
INK    = "#212529"


def box(ax, x, y, w, h, title, sub=None, color=TEAL, title_color="white",
        title_size=13, sub_size=9.5, lw=0):
    """Rounded flat box with a bold title and optional subtitle lines."""
    p = FancyBboxPatch((x, y), w, h,
                       boxstyle="round,pad=0.02,rounding_size=0.06",
                       facecolor=color, edgecolor="white", linewidth=lw)
    ax.add_patch(p)
    if sub:
        ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center",
                fontsize=title_size, fontweight="bold", color=title_color)
        ax.text(x + w / 2, y + h * 0.30, sub, ha="center", va="center",
                fontsize=sub_size, color=title_color)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center",
                fontsize=title_size, fontweight="bold", color=title_color)
    return p


def arrow(ax, x1, y1, x2, y2, color=GREY, lw=3.5, style="-|>", curved=0.0):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style, mutation_scale=22,
        color=color, linewidth=lw,
        connectionstyle=f"arc3,rad={curved}",
    ))


def lane_label(ax, x, y, text, color=INK):
    ax.text(x, y, text, fontsize=10.5, fontweight="bold", color=color,
            style="italic")


def new_fig(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    return fig, ax


def save(fig, name):
    fig.savefig(OUT / name, dpi=200, facecolor="white",
                bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print("wrote", OUT / name)


# ---------------------------------------------------------------- 1. stack
def tech_stack():
    fig, ax = new_fig(13, 8.6)
    ax.text(5, 9.55, "RefurbIQ — Technology Stack", ha="center",
            fontsize=20, fontweight="bold", color=NAVY)

    layers = [
        ("USER INTERFACE", "Streamlit web app  ·  8 interactive tabs", CORAL,
         [("Overview", "Upload Reviews", "Review Analyzer", "Analytics Dashboard"),
          ("Compare Platforms", "Best Place to Buy",
           "Explain Recommendation", "Methodology")]),
        ("ANALYSIS ENGINE", "src/absa.py  ·  src/recommendation.py", TEAL,
         [("Keyword aspect detection", "13 aspects", "3 categories",
           "Whole-review sentiment"),
          ("BERT sentiment model", "Lexicon fallback", "6 weighted sub-scores",
           "HIGH / MEDIUM / LOW confidence")]),
        ("MODELS", "Hugging Face transformers  ·  PyTorch", PURPLE,
         [("cardiffnlp/twitter-roberta-\nbase-sentiment-latest",
           "zero-shot sentiment"),
          ("distilbert-base-uncased", "fine-tuned (1 epoch)"),
          ("TF-IDF + Logistic Regression /\nRandom Forest / XGBoost",
           "classical baselines")]),
        ("DATA & TOOLING", "pandas  ·  matplotlib  ·  scikit-learn", NAVY,
         [("reviews.csv (synthetic demo,\nclearly labelled)",
           "aspect_annotations.csv"),
          ("MARC real Amazon reviews", "pipeline validation"),
          ("GitHub CI-friendly repo", ".venv + scripts")]),
    ]

    y = 8.5
    for name, sub, color, rows in layers:
        box(ax, 0.4, y - 1.75, 9.2, 1.75, "", color=color)
        ax.text(0.75, y - 0.32, name, fontsize=13, fontweight="bold",
                color="white")
        ax.text(0.75, y - 0.72, sub, fontsize=9.5, color="white", alpha=0.9)
        # inner chips: first line of each group bold, remaining lines grey
        n = len(rows)
        chip_w = 8.4 / n
        for i, items in enumerate(rows):
            cx = 0.8 + i * chip_w
            p = FancyBboxPatch((cx, y - 1.62), chip_w - 0.15, 0.78,
                               boxstyle="round,pad=0.01,rounding_size=0.05",
                               facecolor="white", edgecolor="none", alpha=0.94)
            ax.add_patch(p)
            mid = cx + (chip_w - 0.15) / 2
            ax.text(mid, y - 1.02, items[0], ha="center", va="center",
                    fontsize=8.6, fontweight="bold", color=INK)
            if len(items) > 1:
                ax.text(mid, y - 1.42, "\n".join(items[1:]), ha="center",
                        va="center", fontsize=7.8, color=GREY)
        if name != "DATA & TOOLING":
            arrow(ax, 5, y - 1.8, 5, y - 2.18, color=GREY)
        y -= 2.25

    save(fig, "1_diagram_tech_stack.png")


# ---------------------------------------------------------------- 2. workflow
def app_workflow():
    fig, ax = new_fig(13, 8.4)
    ax.text(5, 9.5, "RefurbIQ — End-to-End App Workflow", ha="center",
            fontsize=20, fontweight="bold", color=NAVY)

    # top row: data in -> ABSA
    box(ax, 0.3, 7.0, 2.1, 1.5, "User uploads\nreview CSV",
        sub="or bundled demo dataset", color=CORAL)
    box(ax, 3.1, 7.0, 2.1, 1.5, "Pre-processing",
        sub="clean_reviews() · validate columns", color=ORANGE)
    box(ax, 5.9, 7.0, 2.1, 1.5, "Aspect extraction",
        sub="keyword vocabulary · 13 aspects", color=TEAL)
    box(ax, 8.55, 7.0, 1.25, 1.5, "Sentiment\nmodel", sub="BERT / fallback",
        color=PURPLE, title_size=11.5)
    arrow(ax, 2.4, 7.75, 3.1, 7.75)
    arrow(ax, 5.2, 7.75, 5.9, 7.75)
    arrow(ax, 8.0, 7.75, 8.55, 7.75)

    # middle: ABSA results
    arrow(ax, 6.95, 6.95, 5.5, 6.35)
    box(ax, 3.1, 4.9, 3.8, 1.4, "ABSA results table",
        sub="review × aspect × sentiment × confidence", color=NAVY)

    # branch left: analytics, branch right: recommendation
    arrow(ax, 3.6, 4.9, 2.0, 4.2, curved=-0.15)
    arrow(ax, 6.4, 4.9, 8.0, 4.2, curved=0.15)

    box(ax, 0.4, 2.75, 3.2, 1.45, "Analytics Dashboard",
        sub="sentiment by aspect / platform / category", color=TEAL)
    box(ax, 6.4, 2.75, 3.3, 1.45, "Recommendation Engine",
        sub="6 weighted sub-scores (0–10) per platform", color=CORAL)

    # bottom row: consumer-facing tabs
    arrow(ax, 8.05, 2.7, 2.5, 2.0, curved=0.15, lw=2.5)
    arrow(ax, 8.05, 2.7, 5.0, 2.0, curved=0.1, lw=2.5)
    arrow(ax, 8.05, 2.7, 7.5, 2.0, curved=0.0, lw=2.5)
    box(ax, 1.5, 0.55, 2.0, 1.4, "Compare\nPlatforms", color=ORANGE,
        title_size=11.5)
    box(ax, 4.0, 0.55, 2.0, 1.4, "Best Place\nto Buy", color=GREEN,
        title_size=11.5)
    box(ax, 6.5, 0.55, 2.0, 1.4, "Explain\nRecommendation", color=PINK,
        title_size=11.5)

    # confidence note
    box(ax, 0.4, 0.55, 0.9, 1.4, "", color="none")
    box(ax, 8.75, 0.8, 1.15, 1.0, "Confidence\nHIGH / MED / LOW",
        color=GREY, title_size=8.5)

    save(fig, "2_diagram_app_workflow.png")


# ---------------------------------------------------------------- 3. research
def research_pipeline():
    fig, ax = new_fig(13, 9.2)
    ax.text(5, 9.6, "RefurbIQ — Research & Model Evaluation Pipeline",
            ha="center", fontsize=19, fontweight="bold", color=NAVY)

    steps = [
        ("1 · Platform verification", "Cashify · Amazon Renewed · Flipkart\nOLX · Budli — no public structured reviews", CORAL),
        ("2 · Data strategy", "synthetic demonstration corpus (labelled)\n2,000 reviews · 5 platforms · 3 categories", ORANGE),
        ("3 · Aspect annotation", "9-aspect taxonomy · 3,548 evidence phrases\npositive / neutral / negative", TEAL),
        ("4 · Review-level split", "stratified 70 / 15 / 15 (seed 42)\n2,475 / 536 / 537 — no leakage", NAVY),
        ("5 · Feature + models", "TF-IDF (1–2 grams, 20k features)\nLR · RF · XGBoost  vs  DistilBERT (zs + ft)", PURPLE),
        ("6 · Evaluation", "macro P/R/F1 + per-class recall\nneutral class = hard case", GREEN),
        ("7 · Real-review validation", "2,000 real Amazon reviews (MARC)\n75.6% agreement with star ratings", PINK),
    ]

    y = 8.7
    for title, sub, color in steps:
        box(ax, 1.2, y - 1.02, 7.6, 1.02, "", color=color)
        ax.text(1.55, y - 0.30, title, fontsize=12.5, fontweight="bold",
                color="white")
        ax.text(1.55, y - 0.72, sub.replace("\n", "  ·  "), fontsize=8.8,
                color="white", alpha=0.95)
        if title != steps[-1][0]:
            arrow(ax, 5, y - 1.06, 5, y - 1.30, color=GREY, lw=3)
        y -= 1.22

    # side note
    box(ax, 0.15, 3.4, 0.85, 2.6, "repro-\nducible\nscripts", color=GREY,
        title_size=9)
    save(fig, "3_diagram_research_pipeline.png")


# ---------------------------------------------------------------- 4. recommendation
def recommendation():
    fig, ax = new_fig(13, 8.0)
    ax.text(5, 9.5, "Recommendation Engine — How a Platform is Scored",
            ha="center", fontsize=19, fontweight="bold", color=NAVY)

    # inputs
    box(ax, 0.4, 6.9, 2.6, 1.6, "ABSA results",
        sub="aspect × sentiment counts\nper platform × product", color=TEAL)

    # six sub-scores
    subs = [
        ("Sentiment", "0.25", CORAL),
        ("Product quality", "0.25", CORAL),
        ("Service", "0.15", ORANGE),
        ("Value", "0.15", ORANGE),
        ("Trust", "0.10", PURPLE),
        ("Return / refund", "0.10", PURPLE),
    ]
    x0 = 3.6
    for i, (name, w, color) in enumerate(subs):
        cx = x0 + (i % 3) * 2.15
        cy = 7.75 if i < 3 else 6.75
        box(ax, cx, cy, 2.0, 0.85, f"{name}  ({w})", color=color,
            title_size=10.5)
        arrow(ax, 3.0, 7.7, cx, cy + 0.42, curved=0.1, lw=2.5)

    # formula
    arrow(ax, 6.5, 6.7, 6.5, 6.0)
    box(ax, 3.4, 4.6, 6.2, 1.35, "Sub-score = (pos% × 1.0 + neutral% × 0.5 + neg% × 0.0) × 10",
        sub="Overall score 0–10 = weighted sum of the six sub-scores",
        color=NAVY, title_size=12)

    # confidence gate
    arrow(ax, 6.5, 4.55, 6.5, 3.95)
    box(ax, 3.4, 2.6, 6.2, 1.3, "Confidence gate",
        sub="HIGH: ≥50 reviews + consistent sentiment   ·   MEDIUM: ≥20   ·   LOW: excluded",
        color=GREY, title_size=12)

    # outputs
    outs = [("Rank platforms", TEAL), ("Best Place to Buy", GREEN),
            ("Explain why", PINK)]
    for i, (t, c) in enumerate(outs):
        bx = 1.6 + i * 2.6
        arrow(ax, 6.5, 2.55, bx + 1.0, 1.75, curved=0.12 * (i - 1))
        box(ax, bx, 0.5, 2.0, 1.25, t, color=c, title_size=12)

    save(fig, "4_diagram_recommendation.png")


# ---------------------------------------------------------------- 5. heatmap
def platform_heatmap():
    """Aspect x platform net-sentiment heatmap for the results slide.

    Rendered from the same annotation outputs that build Table 6
    (aspect_annotations.csv x reviews.csv marketplace); the per-platform
    negative-share extremes are cross-checked against
    research/tables/table6_cross_platform.csv before saving.
    """
    import pandas as pd
    from matplotlib.colors import LinearSegmentedColormap

    repo = OUT.parent
    ann = pd.read_csv(repo / "research" / "data" / "aspect_annotations.csv")
    rev = pd.read_csv(repo / "research" / "data" / "reviews.csv")
    t2 = pd.read_csv(repo / "research" / "tables" / "table2_aspect_frequency.csv")
    t6 = pd.read_csv(repo / "research" / "tables" / "table6_cross_platform.csv")
    aspects = [a for a in t2.Aspect if a != "Total"]
    t6i = t6.set_index("Platform")
    platforms = [p for p in t6i.index if p != "Total"]

    df = ann.merge(rev[["review_id", "marketplace"]], on="review_id")
    net, negshare = {}, {}
    for p in platforms:
        for a in aspects:
            sub = df[(df.marketplace == p) & (df.aspect == a)]
            n = len(sub)
            pos = int((sub.sentiment == "positive").sum())
            neg = int((sub.sentiment == "negative").sum())
            net[(p, a)] = 100.0 * (pos - neg) / n if n else 0.0
            negshare[(p, a)] = 100.0 * neg / n if n else 0.0

    # Cross-check the extremes against Table 6 (same underlying outputs).
    for p in platforms:
        got_a = max(aspects, key=lambda a: negshare[(p, a)])
        got_v = round(negshare[(p, got_a)], 1)
        exp_a = t6i.loc[p, "Aspect with highest negative share"]
        exp_v = float(t6i.loc[p, "Highest negative share (%)"])
        flag = "OK" if got_a == exp_a and abs(got_v - exp_v) < 0.05 else "MISMATCH"
        print(f"  table6 check {p}: {flag} ({got_a} {got_v} vs {exp_a} {exp_v})")

    vals = [[net[(p, a)] for a in aspects] for p in platforms]
    max_abs = max(abs(v) for row in vals for v in row)
    vmax = -(-max_abs // 10.0) * 10.0  # round up to nearest 10

    cmap = LinearSegmentedColormap.from_list("net", ["#B03A5B", "#FFFFFF", "#1F6F78"])
    fig, ax = plt.subplots(figsize=(13, 7.2))
    im = ax.imshow(vals, cmap=cmap, vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(aspects)))
    ax.set_xticklabels(aspects, rotation=32, ha="right", fontsize=10)
    ax.set_yticks(range(len(platforms)))
    ax.set_yticklabels(platforms, fontsize=11)
    for i, p in enumerate(platforms):
        for j, a in enumerate(aspects):
            v = vals[i][j]
            ax.text(j, i, f"{v:+.1f}", ha="center", va="center", fontsize=9.5,
                    color="white" if abs(v) > 0.62 * vmax else INK)
    cbar = fig.colorbar(im, ax=ax, shrink=0.82)
    cbar.set_label("net sentiment = positive % - negative %", fontsize=10)
    ax.set_title("Aspect x platform net sentiment (synthetic demo corpus)",
                 fontsize=15, fontweight="bold", color=NAVY, pad=12)
    fig.text(0.5, 0.005,
             "Synthetic demonstration corpus - not verified marketplace data",
             ha="center", fontsize=9, color=GREY, style="italic")
    fig.tight_layout()
    save(fig, "5_diagram_platform_aspect_heatmap.png")


if __name__ == "__main__":
    tech_stack()
    app_workflow()
    research_pipeline()
    recommendation()
    platform_heatmap()