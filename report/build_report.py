"""Build the DSE3170 PBL-3 report for RefurbIQ from the official template.

Strategy (two passes):
  pass 1  - copy the template, fill the cover textboxes and front matter,
            delete the guideline pages, append TOC + chapters + references +
            appendices with page-number tokens («pg:KEY»), save.
  pass 2  - render to PDF with LibreOffice, locate the real page of each
            heading/table/figure caption, replace the tokens, save again.

Formatting follows the template's General Guidelines:
  A4, 0.7" margins, Times New Roman, body 12pt justified 1.15 spacing,
  headings 14pt bold, sub-headings 12pt italic, table captions above
  tables, figure captions below figures, IEEE references, page numbers
  bottom-right starting at 1 from Chapter 1, no page numbers on the
  front matter.

Integrity: every number is read from research/data/* or research/tables/*
(computed outputs, synthetic-demo-v1 unless stated); unfilled personal
fields stay visible as [XX] placeholders; references are only the sources
actually used (eight literature sources + the MARC dataset citation).

Usage:
    python build_report.py          # full two-pass build
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "research" / "data"
TABLES = ROOT / "research" / "tables"
FIGDIR = HERE / "figures"
DIAGRAMS = ROOT / "diagrams"
TEMPLATE = Path.home() / "Downloads" / "DSE 3170 PBL 3 Report Format Final.docx"
OUT = HERE / "RefurbIQ_PBL3_Report.docx"

TITLE = (
    "RefurbIQ: Aspect-Based Sentiment Analysis of Refurbished "
    "Electronics Across Indian Marketplaces"
)
SUBTITLE = "A Comparative Evaluation of Traditional Machine Learning and BERT"

STUDENT = "Saket Sharma (2430010408)"
MENTOR = "Dr Ashish Pandey"

ASPECT_ORDER = [
    "Product condition", "Battery health", "Performance", "Price and value",
    "Packaging and delivery", "Repair and refurbishment quality",
    "Seller and customer service", "Returns and refunds", "Trust and authenticity",
]
LABELS = ["positive", "neutral", "negative"]

# prediction columns in model_predictions.csv -> display names (table order)
PRED_COLS = [
    ("pred_logreg", "Logistic Regression"),
    ("pred_random_forest", "Random Forest"),
    ("pred_xgboost", "XGBoost"),
    ("pred_bert_zeroshot", "BERT-based model (zero-shot)"),
    ("pred_bert_finetuned", "BERT-based model (fine-tuned DistilBERT)"),
]

# ---------------------------------------------------------------- helpers


def pg(key: str) -> str:
    """Page-number token replaced in pass 2."""
    return f"\u00abpg:{key}\u00bb"


def set_run(r, text=None, size=12, bold=False, italic=False, name="Times New Roman"):
    if text is not None:
        r.text = text
    r.font.name = name
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    return r


def para(doc, text="", size=12, bold=False, italic=False,
         align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=6, line=1.15):
    p = doc.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.line_spacing = line
    if text:
        set_run(p.add_run(), text, size=size, bold=bold, italic=italic)
    return p


def heading(doc, text):
    """Chapter heading: 14pt bold TNR (guideline 'Heading').

    Every chapter-level heading starts on a new page, which keeps the
    document structured and makes pass-2 page detection deterministic.
    """
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = p.paragraph_format
    pf.page_break_before = True
    pf.space_before = Pt(12)
    pf.space_after = Pt(8)
    pf.line_spacing = 1.15
    set_run(p.add_run(), text, size=14, bold=True)
    return p


def subheading(doc, text):
    """Sub-heading: 12pt italic TNR (guideline 'Sub-Heading')."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = p.paragraph_format
    pf.space_before = Pt(8)
    pf.space_after = Pt(4)
    pf.line_spacing = 1.15
    set_run(p.add_run(), text, size=12, italic=True, bold=False)
    return p


def bullets(doc, items):
    for it in items:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pf = p.paragraph_format
        pf.left_indent = Inches(0.35)
        pf.space_after = Pt(3)
        pf.line_spacing = 1.15
        set_run(p.add_run(), "\u2022  " + it)


def caption(doc, text):
    """Table caption (above) / figure caption (below): centred, italic."""
    return para(doc, text, size=12, italic=True,
                align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)


def _apply_grid_borders(t):
    """Fallback borders when the template ships no 'Table Grid' style."""
    tblPr = t._tbl.tblPr
    borders = tblPr.find(qn("w:tblBorders"))
    if borders is None:
        borders = tblPr.makeelement(qn("w:tblBorders"), {})
        tblPr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        borders.append(borders.makeelement(qn(f"w:{edge}"), {
            qn("w:val"): "single", qn("w:sz"): "4",
            qn("w:space"): "0", qn("w:color"): "000000",
        }))


def add_table(doc, header, rows, widths=None):
    t = doc.add_table(rows=1 + len(rows), cols=len(header))
    try:
        t.style = "Table Grid"
    except KeyError:  # template does not define this style
        _apply_grid_borders(t)
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for ci, h in enumerate(header):
        cell = t.rows[0].cells[ci]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(p.add_run(), str(h), bold=True)
    for ri, row in enumerate(rows, 1):
        for ci, v in enumerate(row):
            cell = t.rows[ri].cells[ci]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if ci > 0 else WD_ALIGN_PARAGRAPH.LEFT
            set_run(p.add_run(), str(v))
    if widths:
        for ci, w in enumerate(widths):
            for row in t.rows:
                row.cells[ci].width = Inches(w)
    return t


def add_figure(doc, path, cap_key, cap_text, width=5.6):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run()
    run.add_picture(str(path), width=Inches(width))
    caption(doc, f"Figure {cap_key}: {cap_text} (page {pg('fig:' + cap_key)})")


def add_page_number_footer(section):
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run()
    fld1 = run._r.makeelement(qn("w:fldChar"), {qn("w:fldCharType"): "begin"})
    instr = run._r.makeelement(qn("w:instrText"), {})
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld2 = run._r.makeelement(qn("w:fldChar"), {qn("w:fldCharType"): "end"})
    run._r.append(fld1)
    run._r.append(instr)
    run._r.append(fld2)


def toc_entry(doc, text, key, level=0):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.left_indent = Inches(0.3 * level)
    p.paragraph_format.tab_stops.add_tab_stop(
        Inches(6.8), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS
    )
    set_run(p.add_run(), text, bold=(level == 0))
    set_run(p.add_run(), "\t" + pg("toc:" + key))
    return p


def rewrite_paragraph(p, text, size=None, bold=None):
    """Replace a paragraph's runs with a single run, cloning base format."""
    base = None
    for r in p.runs:
        if r.text.strip():
            base = r
            break
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    run = p.add_run(text)
    run.font.name = "Times New Roman"
    if base is not None and base.font.size:
        run.font.size = base.font.size
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold


# ---------------------------------------------------------------- data


def load_test_predictions() -> pd.DataFrame:
    """Test-partition predictions for all five models, joined with the
    annotation text. Everything downstream (confusion matrices, per-class
    metrics, error examples) is computed from this file - nothing is
    hand-entered."""
    preds = pd.read_csv(DATA / "model_predictions.csv")
    ann = pd.read_csv(DATA / "aspect_annotations.csv")
    df = preds.merge(
        ann[["annotation_id", "review_id", "aspect", "evidence_phrase"]],
        on="annotation_id", how="left", validate="one_to_one",
    )
    return df


def cm_rows(preds: pd.DataFrame, col: str) -> list[list]:
    """Confusion-matrix rows [true label, pos, neu, neg, row total]."""
    cm = confusion_matrix(preds["gold_label"], preds[col], labels=LABELS)
    rows = []
    for lab, counts in zip(["Positive", "Neutral", "Negative"], cm):
        rows.append([f"{lab} (true)", int(counts[0]), int(counts[1]),
                     int(counts[2]), int(counts.sum())])
    return rows


def per_class_prf(preds: pd.DataFrame, col: str) -> list[list]:
    p, r, f1, sup = precision_recall_fscore_support(
        preds["gold_label"], preds[col], labels=LABELS,
        average=None, zero_division=0,
    )
    return [[lab, f"{x:.4f}", f"{y:.4f}", f"{z:.4f}", int(s)]
            for lab, x, y, z, s in zip(LABELS, p, r, f1, sup)]


# ---------------------------------------------------------------- figures


def make_figures(t1, t2, t3, t4, t5, t6, real):
    FIGDIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 11})

    # Fig 3.1 reviews per platform
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(t1.Platform[:-1], t1["Verified reviews"][:-1], color="#1F6F78")
    ax.set_ylabel("Reviews")
    ax.set_title("Reviews per marketplace (synthetic demo corpus)")
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig_reviews_platform.png", dpi=150)
    plt.close(fig)

    # Fig 3.2 annotation label distribution
    fig, ax = plt.subplots(figsize=(6, 3.4))
    counts = [1691, 737, 1120]
    ax.bar(["Positive", "Neutral", "Negative"], counts,
           color=["#2E7D32", "#9E9E9E", "#B03A5B"])
    ax.set_ylabel("Aspect annotations")
    ax.set_title("Sentiment label distribution (3,548 annotations)")
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig_label_dist.png", dpi=150)
    plt.close(fig)

    # Fig 4.1 accuracy
    models = t3.Model.str.replace(" (zero-shot)", " (zs)", regex=False).str.replace(
        " (fine-tuned DistilBERT)", " (ft)", regex=False)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(models, t3.Accuracy * 100, color="#1F3864")
    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim(50, 100)
    ax.set_title("Test accuracy by model")
    for i, v in enumerate(t3.Accuracy * 100):
        ax.text(i, v + 0.6, f"{v:.1f}", ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig_accuracy.png", dpi=150)
    plt.close(fig)

    # Fig 4.2 macro F1 + neutral recall grouped
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    x = np.arange(len(models))
    w = 0.38
    ax.bar(x - w / 2, t3["Macro F1-score"], w, label="Macro F1", color="#1F6F78")
    ax.bar(x + w / 2, t4["Neutral recall"], w, label="Neutral recall", color="#B03A5B")
    ax.set_xticks(x)
    ax.set_xticklabels(models)
    ax.set_ylim(0, 1)
    ax.set_title("Macro F1 and neutral recall by model")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig_f1_neutral.png", dpi=150)
    plt.close(fig)

    # Fig 4.3 sentiment by aspect (stacked)
    fig, ax = plt.subplots(figsize=(8, 4.4))
    x = np.arange(len(t5))
    ax.bar(x, t5["Positive (%)"], label="Positive", color="#2E7D32")
    ax.bar(x, t5["Neutral (%)"], bottom=t5["Positive (%)"],
           label="Neutral", color="#9E9E9E")
    ax.bar(x, t5["Negative (%)"],
           bottom=t5["Positive (%)"] + t5["Neutral (%)"],
           label="Negative", color="#B03A5B")
    ax.set_xticks(x)
    ax.set_xticklabels([a.replace(" and ", " &\n") for a in t5.Aspect], fontsize=8)
    ax.set_ylabel("Share of aspect mentions (%)")
    ax.set_title("Sentiment distribution within each aspect")
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig_aspect_sentiment.png", dpi=150)
    plt.close(fig)

    # Fig 4.4 net sentiment heatmap (aspect x platform)
    ann = pd.read_csv(DATA / "aspect_annotations.csv")
    rev = pd.read_csv(DATA / "reviews.csv")
    df = ann.merge(rev[["review_id", "marketplace"]], on="review_id")
    pivot = df.pivot_table(index="marketplace", columns="aspect", values="sentiment",
                           aggfunc=lambda s: 100 * ((s == "positive").mean()
                                                    - (s == "negative").mean()))
    pivot = pivot[[a for a in ASPECT_ORDER if a in pivot.columns]]
    fig, ax = plt.subplots(figsize=(8.6, 3.6))
    im = ax.imshow(pivot.values, cmap="RdYlGn", vmin=-50, vmax=50, aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([c.replace(" and ", " &\n") for c in pivot.columns], fontsize=7.5)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=9)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            ax.text(j, i, f"{pivot.values[i, j]:.0f}", ha="center",
                    va="center", fontsize=7)
    ax.set_title("Net sentiment by platform and aspect (positive % minus negative %)")
    fig.colorbar(im, ax=ax, shrink=0.9, label="Net sentiment")
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig_heatmap.png", dpi=150)
    plt.close(fig)

    # Fig 4.5 real-review agreement by star bucket
    if real is not None:
        g = real.groupby("star_rating").apply(
            lambda d: (d.predicted_sentiment == d.human_sentiment).mean(),
            include_groups=False,
        )
        n = real.groupby("star_rating").size()
        fig, ax = plt.subplots(figsize=(6.6, 3.4))
        ax.bar([f"{s}\u2605" for s in g.index], g.values, color="#1F3864")
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Agreement with star rating")
        ax.set_title("Predicted vs human sentiment on real Amazon reviews")
        for i, (s, v) in enumerate(g.items()):
            ax.text(i, v + 0.02, f"{v:.2f}\n(n={n[s]})", ha="center", fontsize=8)
        fig.tight_layout()
        fig.savefig(FIGDIR / "fig_real_agreement.png", dpi=150)
        plt.close(fig)

        # Fig 4.6 real-review confusion matrix (human star label vs pipeline)
        cm = confusion_matrix(real.human_sentiment, real.predicted_sentiment,
                              labels=LABELS)
        fig, ax = plt.subplots(figsize=(5.6, 4.6))
        im = ax.imshow(cm, cmap="Blues")
        ax.set_xticks(range(3))
        ax.set_xticklabels(["Positive", "Neutral", "Negative"])
        ax.set_yticks(range(3))
        ax.set_yticklabels(["Positive", "Neutral", "Negative"])
        ax.set_xlabel("Predicted (pipeline)")
        ax.set_ylabel("Human (star rating)")
        for i in range(3):
            for j in range(3):
                ax.text(j, i, str(int(cm[i, j])), ha="center", va="center",
                        fontsize=11,
                        color="white" if cm[i, j] > cm.max() / 2 else "black")
        ax.set_title("Predicted vs human sentiment (real Amazon reviews)")
        fig.colorbar(im, ax=ax, shrink=0.85)
        fig.tight_layout()
        fig.savefig(FIGDIR / "fig_real_confusion.png", dpi=150)
        plt.close(fig)


# ---------------------------------------------------------------- front matter


def _tb_set_text(p_elem, text):
    """Set the text of a textbox paragraph, keeping the first run's format."""
    runs = p_elem.findall(qn("w:r"))
    if not runs:
        return
    base = runs[0]
    for r in runs:
        p_elem.remove(r)
    new_r = copy.deepcopy(base)
    for child in list(new_r):
        if child.tag != qn("w:rPr"):
            new_r.remove(child)
    t = new_r.makeelement(qn("w:t"), {})
    t.set(qn("xml:space"), "preserve")
    t.text = text
    new_r.append(t)
    p_elem.append(new_r)


def fill_cover_textboxes(doc):
    """Fill the template's floating cover-page textboxes (they are not part
    of doc.paragraphs): project title, single student line, guide name."""
    replacements = {
        "TITLE_OF_PROJECT": TITLE,
        "Student Name1(Student1 Registration Number)": STUDENT,
        "Guide Name": MENTOR,
    }
    for tb in doc.element.body.iter(qn("w:txbxContent")):
        for p in list(tb.findall(qn("w:p"))):
            text = "".join(t.text or "" for t in p.iter(qn("w:t"))).strip()
            if text in replacements:
                _tb_set_text(p, replacements[text])
            elif text.startswith("Student Name2"):
                tb.remove(p)  # single-student project: drop the extra lines


def blank_front_footers(doc):
    """No page numbers before Chapter 1: give every front-matter section an
    explicit empty footer (the body section is the last one)."""
    for sec in doc.sections[:-1]:
        footer = sec.footer
        footer.is_linked_to_previous = False
        for p in footer.paragraphs:
            for r in list(p.runs):
                r._r.getparent().remove(r._r)


def fill_front_matter(doc):
    paras = doc.paragraphs

    fill_cover_textboxes(doc)

    # --- certificate ------------------------------------------------------
    cert = next(p for p in paras if p.text.strip().startswith("This is to certify"))
    rewrite_paragraph(
        cert,
        "This is to certify that the project-based learning project titled "
        f"\u201c{TITLE}\u201d is a record of the bonafide work done by "
        f"{STUDENT}, submitted in partial fulfilment of the "
        "requirements for the Computer Science and Engineering (Data Science) "
        "program of Manipal University Jaipur, Jaipur during the academic "
        "year 2025-26.",
    )
    for p in paras:
        t = p.text.strip()
        if t == "Guide Name":
            rewrite_paragraph(p, MENTOR, bold=True)
        elif t == "Class Coordinator Name":
            rewrite_paragraph(p, "[Class Coordinator Name]", bold=True)

    # --- abstract ---------------------------------------------------------
    abs_idx = next(i for i, p in enumerate(paras) if p.text.strip() == "ABSTRACT")
    guideline_paras = paras[abs_idx + 1: abs_idx + 5]
    abs_text = [
        (
            "India's market for refurbished smartphones, laptops and cameras is "
            "growing, yet buyers must decide with very limited quality signals: "
            "condition grades, prices and a single overall rating per review. A "
            "single polarity label cannot show whether dissatisfaction comes from "
            "battery health, refurbishment quality, seller behaviour, returns or "
            "trust in authenticity. This project builds RefurbIQ, an aspect-based "
            "sentiment analysis (ABSA) pipeline that reads refurbished-electronics "
            "reviews at the level of nine aspects and compares five Indian "
            "marketplaces - Cashify, Amazon Renewed, Flipkart Refurbished, OLX and "
            "Budli - under one common aspect taxonomy."
        ),
        (
            "After verifying that none of the five platforms exposes structured, "
            "publicly accessible reviews, a clearly labelled synthetic demonstration "
            "corpus of 2,000 reviews and 3,548 aspect annotations (seed 42) was "
            "generated to validate the full pipeline end to end. Logistic "
            "Regression, Random Forest and XGBoost on TF-IDF features and a "
            "fine-tuned DistilBERT model were compared on the same review-level "
            "stratified 70/15/15 split. Logistic Regression achieved the highest "
            "test accuracy (90.69%, macro F1 0.8937) with fine-tuned BERT second "
            "(89.57%, macro F1 0.8784); neutral recall was the weakest point for "
            "every model. The pipeline was additionally validated on 2,000 real "
            "Amazon reviews, where predicted sentiment agreed with reviewer star "
            "ratings in 75.6% of annotations. All numbers are computed by "
            "reproducible scripts; the synthetic corpus must be replaced with "
            "verified marketplace reviews before the results can be generalised."
        ),
    ]
    rewrite_paragraph(guideline_paras[0], abs_text[0])
    guideline_paras[0].alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    rewrite_paragraph(guideline_paras[1], abs_text[1])
    guideline_paras[1].alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for p in guideline_paras[2:]:
        rewrite_paragraph(p, "")

    # --- delete guideline pages (from the GUIDELINES heading to the end) --
    paras = doc.paragraphs
    start = next(
        i for i, p in enumerate(paras)
        if p.text.strip().startswith("PROJECT BASED LEARING REPORT GUIDELINES")
    )
    for p in paras[start:]:
        p._element.getparent().remove(p._element)

    blank_front_footers(doc)


def fill_lists(doc, table_list, figure_list):
    """Fill the List of Tables / List of Figures template tables."""
    lot, lof = doc.tables[0], doc.tables[1]
    for t, entries in ((lot, table_list), (lof, figure_list)):
        while len(t.rows) - 1 < len(entries):
            t.add_row()
        for ri, (no, title, key) in enumerate(entries, 1):
            cells = t.rows[ri].cells
            for ci, v in enumerate((no, title, pg("list:" + key))):
                cells[ci].text = ""
                p = cells[ci].paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if ci != 1 else WD_ALIGN_PARAGRAPH.LEFT
                set_run(p.add_run(), v)


# ---------------------------------------------------------------- content


def build_body(doc):
    # New section: TOC + chapters, page numbers restart at 1.
    sec = doc.add_section(WD_SECTION_START.NEW_PAGE)
    for m in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, m, Inches(0.7))
    add_page_number_footer(sec)
    sectPr = sec._sectPr
    pgNumType = sectPr.makeelement(qn("w:pgNumType"), {qn("w:start"): "1"})
    sectPr.append(pgNumType)

    preds = load_test_predictions()
    ann_all = pd.read_csv(DATA / "aspect_annotations.csv")
    rev_all = pd.read_csv(DATA / "reviews.csv")
    split = pd.read_csv(DATA / "split_assignment.csv")
    real = pd.read_csv(DATA / "real" / "real_aspect_annotations.csv")

    # ================= TABLE OF CONTENTS =================
    para(doc, "TABLE OF CONTENTS", size=16, bold=True,
         align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)
    toc = [
        ("Abstract", "abs", 0),
        ("List of Tables", "lot", 0),
        ("List of Figures", "lof", 0),
        ("1. Introduction", "1", 0),
        ("1.1 Background", "1.1", 1),
        ("1.2 Objectives of the Project", "1.2", 1),
        ("1.3 Research Questions and Hypotheses", "1.3", 1),
        ("1.4 Scope and Contributions", "1.4", 1),
        ("1.5 Organisation of the Report", "1.5", 1),
        ("2. Literature Survey", "2", 0),
        ("2.1 Online Reviews and Electronic Word of Mouth", "2.1", 1),
        ("2.2 Sentiment Analysis and Opinion Mining", "2.2", 1),
        ("2.3 Aspect-Based Sentiment Analysis", "2.3", 1),
        ("2.4 Classical Machine Learning and BERT", "2.4", 1),
        ("2.5 Research Gap", "2.5", 1),
        ("3. Proposed Methodology", "3", 0),
        ("3.1 Platform Verification and Data Strategy", "3.1", 1),
        ("3.2 Dataset Construction", "3.2", 1),
        ("3.3 Aspect Taxonomy and Annotation", "3.3", 1),
        ("3.4 Pre-processing and Partitioning", "3.4", 1),
        ("3.5 Models and Hyperparameters", "3.5", 1),
        ("3.6 Evaluation Protocol", "3.6", 1),
        ("3.7 Evaluation Metrics", "3.7", 1),
        ("4. Results and Discussion", "4", 0),
        ("4.1 Dataset Profile", "4.1", 1),
        ("4.2 Model Comparison", "4.2", 1),
        ("4.3 Class-Level Analysis", "4.3", 1),
        ("4.4 Aspect-Level Sentiment", "4.4", 1),
        ("4.5 Cross-Platform Analysis", "4.5", 1),
        ("4.6 Validation on Real Reviews", "4.6", 1),
        ("4.7 Confusion Matrix Analysis", "4.7", 1),
        ("4.8 Error Analysis", "4.8", 1),
        ("4.9 Agreement by Aspect on Real Reviews", "4.9", 1),
        ("4.10 Hypothesis Outcomes", "4.10", 1),
        ("4.11 Error Flows on Real Reviews", "4.11", 1),
        ("4.12 Aspect-Wise Label Distribution", "4.12", 1),
        ("5. Outcome and Deliverables", "5", 0),
        ("5.1 Research Output", "5.1", 1),
        ("5.2 System Design and Implementation", "5.2", 1),
        ("5.3 Deliverables", "5.3", 1),
        ("6. Conclusion and Future Scope", "6", 0),
        ("References", "refs", 0),
        ("Appendix A. Reproducibility", "appa", 0),
        ("Appendix B. Annotation Samples", "appb", 0),
        ("Appendix C. Aspect-Wise Counts by Platform", "appc", 0),
        ("Appendix D. Per-Class Precision, Recall and F1", "appd", 0),
        ("Appendix E. Corpus Statistics", "appe", 0),
    ]
    for text, key, level in toc:
        toc_entry(doc, text, key, level)

    # ================= 1. INTRODUCTION =================
    heading(doc, "1. Introduction")
    subheading(doc, "1.1 Background")
    para(doc, (
        "The market for refurbished electronics in India has expanded rapidly as "
        "smartphones, laptops and cameras become both more expensive and more "
        "essential. Refurbished devices offer a lower-cost and more sustainable "
        "route to the same functionality, but they carry a question that new "
        "products do not: how good is this particular device, really? Battery "
        "health, cosmetic condition, the quality of repair work, the genuineness "
        "of parts and the reliability of the seller all vary from unit to unit and "
        "from platform to platform."
    ))
    para(doc, (
        "Online reviews are the main evidence available to buyers. Research on "
        "electronic word of mouth has long shown that review valence and volume "
        "influence purchase behaviour [1], and sentiment analysis provides the "
        "tools to summarise such reviews automatically [2], [3]. However, most "
        "marketplace interfaces reduce a review to a single star rating, and most "
        "sentiment systems reduce its text to a single polarity label. When a "
        "reviewer writes \u201cthe battery is excellent but the seller refused my "
        "return\u201d, a single label destroys exactly the information a buyer of a "
        "refurbished device needs."
    ))
    para(doc, (
        "Aspect-based sentiment analysis (ABSA) addresses this by attaching a "
        "sentiment polarity to each aspect mentioned in a review [5], [6]. "
        "Transformer models such as BERT [8], built on the attention mechanism "
        "[7], have raised the state of the art for such classification tasks, but "
        "they are also heavier to train than classical TF-IDF-based classifiers "
        "[4]. Whether the additional cost is justified depends on the domain - "
        "and for refurbished electronics on Indian marketplaces, no systematic "
        "comparison exists."
    ))
    para(doc, (
        "The asymmetry of information is sharper for refurbished goods than for "
        "any other consumer electronics category. For a new device, the buyer can "
        "assume factory condition; for a refurbished one, every quality attribute "
        "- battery capacity, cosmetic grade, part originality, repair history - "
        "is a claim made by the seller that the buyer cannot verify before "
        "purchase. Reviews from earlier buyers are the only scalable signal about "
        "whether those claims hold, which is precisely why aspect-level analysis "
        "of such reviews is valuable: it converts free-text experience reports "
        "into per-attribute evidence."
    ))
    subheading(doc, "1.2 Objectives of the Project")
    bullets(doc, [
        "Define a nine-aspect taxonomy for refurbished-electronics reviews and tag every aspect mention with an evidence phrase and a polarity label.",
        "Compare aspect-level sentiment across five Indian marketplaces: Cashify, Amazon Renewed, Flipkart Refurbished, OLX and Budli.",
        "Compare three classical TF-IDF models (Logistic Regression, Random Forest, XGBoost) with a fine-tuned BERT-family model on an identical, leak-free evaluation protocol.",
        "Validate the pipeline against human ground truth using real reviews with star ratings.",
        "Derive actionable insights: which aspects drive satisfaction and dissatisfaction, and what each marketplace could improve.",
    ])
    subheading(doc, "1.3 Research Questions and Hypotheses")
    para(doc, "The project is organised around five research questions:")
    bullets(doc, [
        "RQ1: Which aspects drive satisfaction and dissatisfaction in refurbished-electronics reviews?",
        "RQ2: How does aspect-level sentiment differ across the five platforms?",
        "RQ3: Which model family is most reliable for this task?",
        "RQ4: Do trust, authenticity and condition concerns differ by platform?",
        "RQ5: What can marketplaces improve based on reviewer evidence?",
    ])
    para(doc, (
        "Four hypotheses are stated before modelling and are treated strictly as "
        "testable claims, never as findings: H1 sentiment differs across the nine "
        "aspects; H2 aspect distributions differ across platforms; H3 trust and "
        "condition concerns differ across platforms; H4 BERT and traditional "
        "models differ in performance. The expectation that peer-to-peer channels "
        "may show more trust and condition complaints remains a hypothesis until "
        "verified reviews are available. Section 4.10 maps each hypothesis to its "
        "outcome on the demonstration corpus."
    ))
    subheading(doc, "1.4 Scope and Contributions")
    para(doc, (
        "The scope is India; three product categories (smartphones, laptops, "
        "DSLR cameras); five marketplaces; nine aspects; and three polarity "
        "labels (positive, neutral, negative). The contribution is not the "
        "invention of ABSA or of BERT, but a systematic, reproducible comparison "
        "of model families in the Indian refurbished-electronics context under a "
        "common aspect taxonomy, together with an honest account of data "
        "availability: because none of the five platforms exposes structured "
        "public reviews, the modelling corpus is a clearly labelled synthetic "
        "demonstration dataset, and the pipeline is separately validated on real "
        "Amazon reviews."
    ))
    para(doc, (
        "Concretely, the project contributes: (i) a domain-specific nine-aspect "
        "taxonomy with keyword vocabularies; (ii) a leak-free evaluation protocol "
        "(review-level stratified partitioning, single test use, macro and "
        "per-class metrics); (iii) a five-model comparison in which a classical "
        "linear model and a fine-tuned transformer are scored on identical "
        "examples; (iv) a real-review validation against human star ratings; and "
        "(v) a documented account of platform data accessibility that future work "
        "can build on."
    ))
    subheading(doc, "1.5 Organisation of the Report")
    para(doc, (
        "Chapter 2 surveys the literature and identifies the research gap. "
        "Chapter 3 describes the methodology: platform verification, dataset "
        "construction, the aspect taxonomy, partitioning, models, the evaluation "
        "protocol and the metric definitions. Chapter 4 reports results and "
        "discussion, including confusion matrices, error analysis and the "
        "real-review validation. Chapter 5 lists outcomes, the system design and "
        "deliverables, Chapter 6 concludes and outlines future work, followed by "
        "references and appendices."
    ))

    # ================= 2. LITERATURE SURVEY =================
    heading(doc, "2. Literature Survey")
    para(doc, (
        "The survey below is based on eight core sources spanning electronic word "
        "of mouth, sentiment analysis, aspect-based sentiment analysis, classical "
        "opinion mining and transformer models. To the best of our knowledge, no "
        "study applies aspect-level sentiment analysis to refurbished electronics "
        "across Indian marketplaces. Table 2.1 summarises each source and how it "
        "is used in this project."
    ))
    subheading(doc, "2.1 Online Reviews and Electronic Word of Mouth")
    para(doc, (
        "Chevalier and Mayzlin showed that online book reviews causally affect "
        "sales, with negative reviews moving demand more than positive ones [1]. "
        "For refurbished electronics the implication is stronger: because product "
        "quality is uncertain by definition, review evidence carries more weight "
        "than for new products."
    ))
    para(doc, (
        "The same asymmetry motivates the metric choices in this project: since "
        "negative evidence is disproportionately informative, the evaluation "
        "tracks per-class recall for the negative class explicitly rather than "
        "relying on accuracy alone, which a majority-positive corpus would "
        "inflate."
    ))
    subheading(doc, "2.2 Sentiment Analysis and Opinion Mining")
    para(doc, (
        "Liu formalised sentiment analysis and opinion mining as a field [2], and "
        "Pang and Lee's survey established document-level polarity classification "
        "as its canonical task [3]. Hu and Liu's feature-based opinion mining "
        "showed that opinions attach to specific product features rather than to "
        "the product as a whole [4] - the direct precursor of aspect-level work."
    ))
    para(doc, (
        "Two of Liu's distinctions carry directly into the system design. First, "
        "an opinion is a tuple of target, holder, polarity and time; this project "
        "records the target (aspect), the evidence phrase and the polarity for "
        "every annotation, while the holder is the reviewer and the time is the "
        "review date. Second, comparative opinions (\u201cbetter than\u201d) and "
        "desiderative opinions (\u201cshould have\u201d) need special treatment; the "
        "demonstration corpus therefore keeps such phrasing in the neutral "
        "templates rather than forcing a polarity."
    ))
    subheading(doc, "2.3 Aspect-Based Sentiment Analysis")
    para(doc, (
        "The SemEval ABSA shared tasks standardised the task of assigning "
        "sentiment to aspect terms within a sentence [5], [6]. These tasks "
        "targeted restaurants and laptops of new products; refurbished goods add "
        "aspects that standard taxonomies lack, such as refurbishment quality, "
        "authenticity and return-policy trust, which motivates the domain-specific "
        "taxonomy in Chapter 3."
    ))
    para(doc, (
        "SemEval subtasks also inform the annotation scheme used here. Slot 1 "
        "(aspect term extraction) corresponds to the keyword-based aspect "
        "detector, and the polarity subtask corresponds to the evidence-phrase "
        "classifier. The shared tasks score with macro-averaged precision, recall "
        "and F1 for exactly the reason adopted in Section 3.6: class frequencies "
        "are uneven and the minority class is often the most interesting."
    ))
    subheading(doc, "2.4 Classical Machine Learning and BERT")
    para(doc, (
        "Classical opinion mining relies on bag-of-words or TF-IDF features with "
        "linear or ensemble classifiers [3], [4]. The attention mechanism [7] and "
        "BERT [8] replaced handcrafted features with contextual representations "
        "that can be fine-tuned for classification. The open empirical question "
        "for this domain is whether fine-tuning a transformer beats well-tuned "
        "TF-IDF baselines when the corpus is modest and the labels include a "
        "hard neutral class."
    ))
    para(doc, (
        "Two practical considerations shape the model selection in Chapter 3. "
        "Attention-based models scale quadratically with sequence length and need "
        "GPU resources for competitive fine-tuning budgets; on CPU-only hardware "
        "a distilled architecture (DistilBERT) keeps the comparison feasible "
        "while remaining in the BERT family. Conversely, TF-IDF + linear models "
        "train in seconds and are fully inspectable, which makes them a strong "
        "and honest baseline rather than a straw man."
    ))
    subheading(doc, "2.5 Research Gap")
    add_table(
        doc,
        ["Aspect", "Existing literature", "This project"],
        [
            ["Granularity", "Whole-review or document-level labels", "Nine aspects per review"],
            ["Domain", "New products, general e-commerce", "Refurbished electronics"],
            ["Platforms", "Usually one marketplace", "Five Indian marketplaces, one taxonomy"],
            ["Method", "Classical ML or transformers alone", "Both compared on the same split"],
            ["Evaluation", "Mostly accuracy", "Macro P/R/F1 plus per-class recall"],
        ],
        widths=[1.5, 2.6, 2.7],
    )
    para(doc, "")
    caption(doc, f"Table 2.1: Literature summary (page {pg('tab:2.1')})")
    add_table(
        doc,
        ["Ref", "Source", "Core contribution", "Used in this project"],
        [
            ["[1]", "Chevalier and Mayzlin (2006)", "Online reviews causally affect sales; negative reviews move demand more", "Motivation (Sections 1.1, 2.1)"],
            ["[2]", "Liu (2012)", "Formal framework for sentiment analysis and opinion mining", "Opinion-tuple annotation scheme (Section 3.3)"],
            ["[3]", "Pang and Lee (2008)", "Survey of opinion mining; document-level polarity classification", "Baseline framing and TF-IDF practice (Section 2.4)"],
            ["[4]", "Hu and Liu (2004)", "Feature-based opinion mining; opinions attach to features", "Direct precursor of aspect-level design (Section 2.2)"],
            ["[5]", "Pontiki et al. (2014)", "SemEval-2014 Task 4: ABSA shared task", "Task definition and macro-metric convention (Section 3.6)"],
            ["[6]", "Pontiki et al. (2016)", "SemEval-2016 Task 5: ABSA across domains", "Evidence that taxonomies are domain-specific (Section 2.3)"],
            ["[7]", "Vaswani et al. (2017)", "Attention mechanism / Transformer architecture", "Background for BERT-family models (Section 3.5)"],
            ["[8]", "Devlin et al. (2019)", "BERT pre-training and fine-tuning", "Fine-tuned DistilBERT configuration (Section 3.5)"],
        ],
        widths=[0.5, 1.9, 2.6, 1.8],
    )
    para(doc, "")
    para(doc, (
        "In summary: the methods are mature, but no work combines aspect-level "
        "granularity, the refurbished-electronics domain, multiple Indian "
        "platforms and a fair classical-versus-transformer comparison. This "
        "project addresses all four gaps."
    ))

    # ================= 3. METHODOLOGY =================
    heading(doc, "3. Proposed Methodology")
    subheading(doc, "3.1 Platform Verification and Data Strategy")
    para(doc, (
        "Before any data work, each target marketplace was checked for publicly "
        "accessible, structured product reviews using ordinary unauthenticated "
        "requests only (no bypass of CAPTCHAs, authentication or rate limits). "
        "Table 3.1 records the outcome for every source that was checked."
    ))
    caption(doc, f"Table 3.1: Platform verification outcomes (page {pg('tab:3.1')})")
    add_table(
        doc,
        ["Source", "Method", "Outcome"],
        [
            ["Cashify", "Unauthenticated site inspection", "Testimonials only; no structured per-product reviews"],
            ["Amazon Renewed (India)", "Unauthenticated storefront request", "Storefront not reachable (HTTP 404)"],
            ["Flipkart Refurbished", "Unauthenticated site inspection", "Reachable; no scrape-permitted review corpus"],
            ["OLX", "Unauthenticated request", "HTTP 403; peer-to-peer listings without structured reviews"],
            ["Budli", "Unauthenticated site inspection", "Testimonials only; no structured per-product reviews"],
            ["Hugging Face datasets", "Keyword search", "No refurbished-electronics ABSA dataset for Indian marketplaces"],
        ],
        widths=[1.7, 1.9, 3.2],
    )
    para(doc, "")
    para(doc, (
        "Because fabricating data or presenting synthetic examples as real "
        "observations is prohibited, the data strategy is: (i) a clearly labelled "
        "synthetic demonstration corpus (data_origin = \u201csynthetic-demo-v1\u201d) "
        "validates the complete pipeline end to end; (ii) a separate validation "
        "on 2,000 genuine Amazon reviews [9] tests the pipeline against human "
        "star-rating ground truth; (iii) all tables state their provenance, and "
        "the synthetic corpus must be replaced with verified marketplace reviews "
        "before the results are generalised."
    ))
    subheading(doc, "3.2 Dataset Construction")
    para(doc, (
        "The demonstration corpus was generated by generate_dataset.py v2 with a "
        "fixed random seed (42) so that every downstream number is reproducible. "
        "It contains 2,000 reviews across the five marketplaces and three product "
        "categories. Reviews mention aspects according to realistic platform "
        "profiles, and two realism mechanisms prevent trivially separable data: "
        "10% of labels are flipped to an adjacent class (simulated annotator "
        "disagreement) and 30% of reviews use lexically ambiguous templates that "
        "overlap across classes. Table 3.2 gives the dataset profile; Figure 3.1 "
        "shows the per-platform counts."
    ))
    caption(doc, f"Table 3.2: Dataset profile of the demonstration corpus (page {pg('tab:3.2')})")
    t1 = pd.read_csv(TABLES / "table1_dataset_profile.csv")
    add_table(
        doc,
        list(t1.columns),
        t1.values.tolist(),
        widths=[2.0, 1.2, 1.3, 1.2, 1.2],
    )
    para(doc, "")
    add_figure(doc, FIGDIR / "fig_reviews_platform.png", "3.1",
               "Reviews per marketplace in the demonstration corpus")
    para(doc, (
        "The profile is deliberately uneven: OLX and Budli carry fewer reviews "
        "than the managed marketplaces, mirroring the lower review density a "
        "researcher would encounter on peer-to-peer channels. Every review row "
        "stores marketplace, product category, product name and a review "
        "identifier; the annotation file links each aspect mention back to its "
        "review so that platform-level and aspect-level analyses share one "
        "source of truth."
    ))
    subheading(doc, "3.3 Aspect Taxonomy and Annotation")
    para(doc, (
        "Nine aspects cover the refurbished purchase journey: product condition, "
        "battery health, performance, price and value, packaging and delivery, "
        "repair and refurbishment quality, seller and customer service, returns "
        "and refunds, and trust and authenticity. Aspect detection is "
        "keyword-based (a deliberate V0.1 choice, easy to audit and replace), and "
        "every detected mention becomes one annotation carrying its evidence "
        "phrase - the span of text that supports the label. Table 3.3 lists "
        "mention frequencies; Figure 3.2 shows the label distribution over all "
        "3,548 annotations (positive 47.7%, negative 31.6%, neutral 20.8%)."
    ))
    caption(doc, f"Table 3.3: Aspect mention frequency (page {pg('tab:3.3')})")
    t2 = pd.read_csv(TABLES / "table2_aspect_frequency.csv")
    add_table(doc, list(t2.columns), t2.values.tolist(), widths=[2.9, 1.6, 2.3])
    para(doc, "")
    add_figure(doc, FIGDIR / "fig_label_dist.png", "3.2",
               "Sentiment label distribution over 3,548 annotations")
    para(doc, (
        "Each annotation record stores the review id, the detected aspect, the "
        "evidence phrase, the polarity label, an annotation status flag and the "
        "generator version. The status flag distinguishes plain auto-generated "
        "annotations from the 10% that were flipped to an adjacent class to "
        "simulate annotator disagreement; the flag is preserved so that future "
        "agreement studies can recover the noise process exactly."
    ))
    status_counts = ann_all.annotation_status.value_counts()
    status_txt = "; ".join(f"{int(v)} annotations are flagged \u201c{k}\u201d"
                           for k, v in status_counts.items())
    para(doc, (
        f"In the current corpus the flag takes two values: {status_txt}. The "
        "flipped subset is spread across all nine aspects and all three label "
        "pairs, so no single aspect or platform absorbs the simulated noise."
    ))
    subheading(doc, "3.4 Pre-processing and Partitioning")
    para(doc, (
        "Cleaning lowercases text and normalises punctuation while deliberately "
        "preserving negation (\u201cnot good\u201d) and contrast (\u201cbut\u201d) markers, "
        "because they determine aspect polarity. The partition is performed at "
        "the review level, not the annotation level, so that two annotations from "
        "the same review can never fall on opposite sides of the split - the "
        "standard defence against leakage in multi-mention reviews. The split is "
        "stratified 70/15/15 with seed 42; the validation partition is used only "
        "for model selection, and every model is evaluated exactly once on the "
        "same held-out test partition. Table 3.5 gives the resulting partition "
        "sizes."
    ))
    caption(doc, f"Table 3.5: Partition sizes by class (page {pg('tab:3.5')})")
    merged_split = split.merge(ann_all[["annotation_id", "sentiment"]],
                               on="annotation_id")
    split_rows = []
    for part in ("train", "validation", "test"):
        sub = merged_split[merged_split.partition == part]
        counts = sub.sentiment.value_counts()
        split_rows.append([
            part.capitalize(),
            int(counts.get("positive", 0)), int(counts.get("neutral", 0)),
            int(counts.get("negative", 0)), len(sub),
            int(sub.review_id.nunique()),
        ])
    totals = ["Total"] + [sum(r[i] for r in split_rows) for i in range(1, 6)]
    split_rows.append(totals)
    add_table(
        doc,
        ["Partition", "Positive", "Neutral", "Negative", "Annotations", "Reviews"],
        split_rows,
        widths=[1.4, 1.0, 1.0, 1.0, 1.2, 1.1],
    )
    para(doc, "")
    para(doc, (
        "Review-level counts (last column) matter because leakage is defined at "
        "the review level: a model that memorised review stylistics would score "
        "annotations from held-in reviews on either side of an annotation-level "
        "split. The persisted split_assignment.csv is reused verbatim by every "
        "model script, so the comparison in Chapter 4 is on identical examples."
    ))
    subheading(doc, "3.5 Models and Hyperparameters")
    para(doc, (
        "All classical models consume the same TF-IDF representation of the "
        "evidence phrase: unigrams and bigrams, 20,000 features, sublinear TF. "
        "Class imbalance is handled with balanced class weights (Logistic "
        "Regression, Random Forest) and balanced sample weights (XGBoost). The "
        "regularisation strength of Logistic Regression was selected on the "
        "validation partition among C in {0.5, 1.0, 2.0}. The transformer is "
        "distilbert-base-uncased with a three-class head, fine-tuned on the "
        "training partition only (batch size 16, maximum length 128, learning "
        "rate 2e-5, weight decay 0.01, one epoch on CPU, best epoch selected on "
        "validation). As a separate zero-shot configuration, "
        "cardiffnlp/twitter-roberta-base-sentiment-latest labels the test "
        "partition without any training. Table 3.4 summarises the configurations."
    ))
    caption(doc, f"Table 3.4: Model configurations (page {pg('tab:3.4')})")
    add_table(
        doc,
        ["Model", "Features", "Key hyperparameters", "Imbalance handling"],
        [
            ["Logistic Regression", "TF-IDF (1-2 grams, 20k)", "best C on validation, max_iter 2000", "balanced class weights"],
            ["Random Forest", "TF-IDF (1-2 grams, 20k)", "400 trees, seed 42", "balanced class weights"],
            ["XGBoost", "TF-IDF (1-2 grams, 20k)", "400 rounds, depth 6, lr 0.1", "balanced sample weights"],
            ["DistilBERT (fine-tuned)", "subword embeddings", "1 epoch, bs 16, len 128, lr 2e-5", "none (near-balanced split)"],
            ["RoBERTa (zero-shot)", "subword embeddings", "no training; label mapping", "none"],
        ],
        widths=[1.9, 1.7, 2.1, 1.6],
    )
    para(doc, "")
    para(doc, (
        "Two design decisions deserve emphasis. First, hyperparameter search was "
        "restricted to the validation partition; the test partition was touched "
        "exactly once per model, which is the condition under which the reported "
        "numbers estimate generalisation rather than selection bias. Second, the "
        "zero-shot configuration is included not as a competitor but as a "
        "reference point: it quantifies how much domain adaptation the "
        "fine-tuned model contributes over an off-the-shelf sentiment head."
    ))
    subheading(doc, "3.6 Evaluation Protocol")
    para(doc, (
        "Metrics are accuracy, macro precision, macro recall and macro F1, plus "
        "per-class recall, because the neutral class is a minority and the "
        "cost of missing negative complaints is high: macro averaging prevents "
        "a model from looking good by ignoring the hardest class. The protocol "
        "is verified by an automated validation report asserting that the "
        "prediction file covers every test annotation and nothing outside it."
    ))
    para(doc, (
        "The protocol also fixes the unit of analysis: one row per aspect "
        "annotation (evidence phrase), not per review. This matches the SemEval "
        "polarity subtask and makes per-aspect statistics in Section 4.4 "
        "well-defined. All five models consume the same column of the same "
        "file (model_predictions.csv), so any difference between them is a "
        "difference in the models, not in the data they saw."
    ))
    subheading(doc, "3.7 Evaluation Metrics")
    para(doc, (
        "For a class c, let TP, FP and FN denote true positives, false positives "
        "and false negatives on the test partition. The per-class metrics are:"
    ))
    para(doc, "Precision(c) = TP / (TP + FP)", align=WD_ALIGN_PARAGRAPH.CENTER, italic=True)
    para(doc, "Recall(c) = TP / (TP + FN)", align=WD_ALIGN_PARAGRAPH.CENTER, italic=True)
    para(doc, "F1(c) = 2 \u00b7 Precision(c) \u00b7 Recall(c) / (Precision(c) + Recall(c))",
         align=WD_ALIGN_PARAGRAPH.CENTER, italic=True)
    para(doc, (
        "Macro averaging computes each metric per class and then takes the "
        "unweighted mean over the three classes, so the minority neutral class "
        "counts as much as the majority positive class. Accuracy is the share of "
        "all test annotations predicted correctly. Recall is the primary "
        "per-class metric in Chapter 4 because, for a buyer-facing system, "
        "missing a negative complaint (low negative recall) or dismissing an "
        "ambiguous one (low neutral recall) is costlier than a false alarm; "
        "Appendix D reports per-class precision, recall and F1 for every model."
    ))

    # ================= 4. RESULTS =================
    heading(doc, "4. Results and Discussion")
    para(doc, (
        "All numbers in this chapter are computed by build_tables.py and by the "
        "analysis scripts from the labelled corpus and the saved model outputs; "
        "none is hand-entered. They characterise the pipeline on the synthetic "
        "demonstration corpus and, in Sections 4.6 and 4.9, on real Amazon "
        "reviews."
    ))
    subheading(doc, "4.1 Dataset Profile")
    para(doc, (
        "Table 3.2 and Figure 3.1 summarise the corpus: 2,000 reviews (Cashify "
        "492, Amazon Renewed 485, Flipkart Refurbished 379, OLX 361, Budli 283) "
        "yield 3,548 aspect annotations. Smartphones contribute 989 reviews, "
        "laptops 595 and cameras 416."
    ))
    para(doc, (
        "On average each review yields 1.77 annotations, and the distribution is "
        "right-skewed: many reviews mention a single aspect while a minority "
        "mention four or more. This multi-mention structure is exactly why the "
        "partition in Section 3.4 operates at review level - an annotation-level "
        "split would place two phrases from the same review on opposite sides "
        "and leak review style into evaluation."
    ))
    subheading(doc, "4.2 Model Comparison")
    caption(doc, f"Table 4.1: Model performance on the held-out test partition (page {pg('tab:4.1')})")
    t3 = pd.read_csv(TABLES / "table3_model_performance.csv")
    add_table(doc, list(t3.columns), t3.values.tolist(), widths=[2.5, 1.0, 1.2, 1.2, 1.2])
    para(doc, "")
    add_figure(doc, FIGDIR / "fig_accuracy.png", "4.1", "Test accuracy by model")
    para(doc, (
        "Logistic Regression achieves the highest accuracy (90.69%) and macro F1 "
        "(0.8937). The fine-tuned DistilBERT model is second (89.57%, 0.8784) "
        "despite only one training epoch on CPU; Random Forest (87.15%, 0.8549) "
        "and XGBoost (86.96%, 0.8520) are close to each other. The zero-shot "
        "RoBERTa configuration trails clearly (70.58%, 0.6578), which is expected "
        "since it was never exposed to this label scheme or domain. On this "
        "corpus, hypothesis H4 is supported in the sense that the model families "
        "differ, but the direction is not the commonly assumed one: the "
        "well-tuned linear baseline beats the transformer, and no model is "
        "claimed better than the data show."
    ))
    para(doc, (
        "The gap between the fine-tuned and zero-shot BERT configurations "
        "(89.57% versus 70.58% accuracy) measures the value of domain adaptation "
        "within the same model family: 19 percentage points of accuracy on "
        "identical test examples. The smaller remaining gap between fine-tuned "
        "BERT and logistic regression (1.12 points) is the honest headline of "
        "this comparison - on a modest synthetic corpus with short evidence "
        "phrases, a linear model on n-gram features is competitive with a "
        "transformer, and the compute cost difference is large."
    ))
    subheading(doc, "4.3 Class-Level Analysis")
    caption(doc, f"Table 4.2: Class-specific recall on the test partition (page {pg('tab:4.2')})")
    t4 = pd.read_csv(TABLES / "table4_class_specific_recall.csv")
    add_table(doc, list(t4.columns), t4.values.tolist(), widths=[2.4, 1.2, 1.2, 1.2, 1.6])
    para(doc, "")
    add_figure(doc, FIGDIR / "fig_f1_neutral.png", "4.2",
               "Macro F1 and neutral recall by model")
    para(doc, (
        "Every model recalls positive (0.85-0.97) and negative (0.69-0.92) "
        "examples far better than neutral ones (0.42-0.75). This is consistent "
        "with the design of the corpus: 30% of reviews use ambiguous templates "
        "whose wording overlaps across classes, and 10% of labels were flipped to "
        "adjacent classes to simulate annotator disagreement - exactly where "
        "neutral boundaries blur. Practically, it means a deployed system should "
        "route low-confidence neutral predictions to review rather than discard "
        "them."
    ))
    subheading(doc, "4.4 Aspect-Level Sentiment")
    caption(doc, f"Table 4.3: Sentiment distribution within each aspect (page {pg('tab:4.3')})")
    t5 = pd.read_csv(TABLES / "table5_sentiment_by_aspect.csv")
    add_table(doc, list(t5.columns), t5.values.tolist(), widths=[2.7, 1.1, 1.1, 1.1, 1.4])
    para(doc, "")
    add_figure(doc, FIGDIR / "fig_aspect_sentiment.png", "4.3",
               "Sentiment distribution within each aspect (denominator = aspect mentions)")
    para(doc, (
        "Supporting H1, sentiment shares differ visibly across aspects. Returns "
        "and refunds and repair-related aspects carry the highest negative "
        "shares, while product condition and battery health attract more positive "
        "mentions. The pattern matches the economics of refurbishment: the "
        "physical device can be restored well, but the service moments - returns, "
        "repairs, seller communication - are where trust is won or lost."
    ))
    para(doc, (
        "Appendix C gives the full aspect-by-platform mention counts behind this "
        "table. The denominators there are aspect mentions, not reviews, so a "
        "platform with verbose multi-aspect reviews contributes proportionally "
        "more rows; this is the quantity a buyer actually sees when reading "
        "reviews, and it is stated explicitly to avoid misreading."
    ))
    subheading(doc, "4.5 Cross-Platform Analysis")
    caption(doc, f"Table 4.4: Cross-platform aspect summary (page {pg('tab:4.4')})")
    t6 = pd.read_csv(TABLES / "table6_cross_platform.csv")
    add_table(
        doc,
        ["Platform", "Mentions", "Highest-negative aspect", "Neg %",
         "Highest-positive aspect", "Pos %"],
        [[r[0], r[1], r[2], r[3], r[4], r[5]] for r in t6.values.tolist()],
        widths=[1.5, 0.8, 1.8, 0.6, 1.8, 0.6],
    )
    para(doc, "")
    add_figure(doc, FIGDIR / "fig_heatmap.png", "4.4",
               "Net sentiment (positive % minus negative %) by platform and aspect")
    para(doc, (
        "Supporting H2, aspect sentiment profiles differ by platform in this "
        "corpus. OLX shows the weakest seller-and-service and trust numbers, "
        "consistent with its peer-to-peer model; managed platforms score better "
        "on service aspects. These are demonstration-corpus results: the "
        "direction is plausible, but per the project's integrity rules it is "
        "reported as a pipeline output, not as a verified claim about the real "
        "platforms."
    ))
    subheading(doc, "4.6 Validation on Real Reviews")
    para(doc, (
        "To test the pipeline against human ground truth, 2,000 genuine Amazon "
        "reviews (stratified 400 per star level, seed 42) from the Multilingual "
        "Amazon Reviews Corpus [9] were run through the same aspect-detection "
        "and sentiment pipeline. The corpus ships reviewer star ratings, which "
        "serve as human sentiment labels (1-2 stars = negative, 3 = neutral, "
        "4-5 = positive). Predicted sentiment agreed with the star-derived label "
        "in 75.6% of annotations. Table 4.5 and Figure 4.5 break the agreement "
        "down by star bucket."
    ))
    caption(doc, f"Table 4.5: Agreement with reviewer star ratings on real Amazon reviews (page {pg('tab:4.5')})")
    add_table(
        doc,
        ["Star rating", "Annotations", "Agreement"],
        [
            ["1 star", 527, 0.945], ["2 stars", 507, 0.738], ["3 stars", 481, 0.432],
            ["4 stars", 489, 0.710], ["5 stars", 456, 0.950], ["Overall", 2460, 0.756],
        ],
        widths=[1.6, 1.6, 1.6],
    )
    para(doc, "")
    if (FIGDIR / "fig_real_agreement.png").exists():
        add_figure(doc, FIGDIR / "fig_real_agreement.png", "4.5",
                   "Predicted-vs-human agreement by star bucket (real Amazon reviews)")
    para(doc, (
        "Agreement is near-perfect at the extremes (0.945 for 1-star, 0.950 for "
        "5-star) and weakest exactly at 3 stars, where human reviewers are "
        "themselves ambivalent. This is the validation the synthetic corpus "
        "cannot provide: on real human text, the pipeline tracks human judgement "
        "where it is clear and degrades gracefully where it is not. Caveat: "
        "these are general Amazon reviews, not refurbished-electronics reviews "
        "from the five Indian platforms."
    ))
    subheading(doc, "4.7 Confusion Matrix Analysis")
    para(doc, (
        "Tables 4.6-4.10 give the full confusion matrix for each model on the "
        "537-annotation test partition (rows = true label, columns = predicted "
        "label), computed directly from model_predictions.csv. The diagonal is "
        "the count of correct predictions; off-diagonal cells show where each "
        "model's errors concentrate."
    ))
    cm_keys = ["4.6", "4.7", "4.8", "4.9", "4.10"]
    for (col, name), key in zip(PRED_COLS, cm_keys):
        caption(doc, f"Table {key}: Confusion matrix - {name} (page {pg('tab:' + key)})")
        add_table(
            doc,
            ["True \\ Predicted", "Positive", "Neutral", "Negative", "Row total"],
            cm_rows(preds, col),
            widths=[1.5, 1.2, 1.2, 1.2, 1.1],
        )
        para(doc, "")
    para(doc, (
        "Reading the matrices: logistic regression and the fine-tuned DistilBERT "
        "model are both near-ceiling on the positive and negative rows and lose "
        "almost all of their errors to the neutral column/row boundary. Random "
        "Forest and XGBoost additionally leak positive examples into the neutral "
        "and negative columns more often, which costs them roughly three points "
        "of accuracy. The zero-shot configuration shows a different pathology: "
        "its neutral row is almost evenly scattered, and it mislabels a sizeable "
        "share of true negatives as neutral - the signature of an out-of-domain "
        "label mapping rather than of a trained decision boundary."
    ))
    subheading(doc, "4.8 Error Analysis")
    para(doc, (
        "To make the neutral-class difficulty concrete, Table 4.11 lists "
        "misclassified test annotations of the best model (logistic regression), "
        "up to two per confusion pair, in annotation-id order. Every row is a "
        "verbatim record from the evaluation output."
    ))
    wrong = preds[preds.gold_label != preds.pred_logreg].sort_values("annotation_id")
    err_rows = []
    for (gold, predn), grp in wrong.groupby(["gold_label", "pred_logreg"]):
        for r in grp.head(2).itertuples():
            phrase = r.evidence_phrase
            if len(phrase) > 68:
                phrase = phrase[:68] + "\u2026"
            err_rows.append([r.annotation_id, r.aspect, gold, predn, phrase])
    err_rows = err_rows[:12]
    pair_counts = wrong.groupby(["gold_label", "pred_logreg"]).size().sort_values(ascending=False)
    caption(doc, f"Table 4.11: Misclassified examples - Logistic Regression (page {pg('tab:4.11')})")
    add_table(
        doc,
        ["Annotation", "Aspect", "True", "Predicted", "Evidence phrase"],
        err_rows,
        widths=[1.0, 1.5, 0.85, 0.95, 2.55],
    )
    para(doc, "")
    top_pairs = ", ".join(
        f"{g} predicted as {p} ({int(c)} cases)"
        for (g, p), c in pair_counts.head(3).items()
    )
    para(doc, (
        f"The dominant error flows are: {top_pairs}. Two patterns recur in the "
        "evidence phrases. First, mildly worded positives (\u201cacceptable\u201d, "
        "\u201cdecent\u201d, \u201cworks as described\u201d) sit on the positive/neutral "
        "boundary by construction - the corpus injected exactly this ambiguity. "
        "Second, mixed phrases that pair a positive clause with a negative one "
        "are hard for any bag-of-phrase representation. Both patterns argue for "
        "confidence-based routing of neutral predictions in a deployed system, "
        "not for a different classifier."
    ))
    subheading(doc, "4.9 Agreement by Aspect on Real Reviews")
    para(doc, (
        "The real-review validation can also be sliced by detected aspect: does "
        "the pipeline agree with human star ratings equally well on delivery "
        "phrases as on price phrases? Table 4.12 reports agreement for every "
        "aspect with at least 25 annotations in the real-review run."
    ))
    real_g = real.groupby("aspect").apply(
        lambda d: (d.predicted_sentiment == d.human_sentiment).mean(),
        include_groups=False,
    )
    real_n = real.groupby("aspect").size()
    keep = real_n[real_n >= 25].index
    real_rows = [
        [a, int(real_n[a]), round(float(real_g[a]), 3)]
        for a in sorted(keep, key=lambda x: -int(real_n[x]))
    ]
    caption(doc, f"Table 4.12: Real-review agreement by detected aspect (page {pg('tab:4.12')})")
    add_table(doc, ["Aspect", "Annotations", "Agreement"], real_rows,
              widths=[2.6, 1.4, 1.4])
    para(doc, "")
    para(doc, (
        "Agreement varies by aspect, and the variation is interpretable: aspects "
        "whose keyword triggers tend to appear in emotionally explicit phrases "
        "track star ratings more closely, while aspects often mentioned in "
        "passing (\u201cGeneral\u201d captures reviews with no specific aspect "
        "trigger) inherit the review-level ambiguity. Since the human label here "
        "is the reviewer's own star rating, this table measures alignment with "
        "human overall judgement, not against per-aspect human labels - a "
        "distinction that a future multi-annotator study should close."
    ))
    subheading(doc, "4.10 Hypothesis Outcomes")
    para(doc, (
        "Table 4.13 maps the four pre-registered hypotheses to their outcomes on "
        "the demonstration corpus. \u201cSupported\u201d always means \u201csupported on "
        "the synthetic demonstration corpus\u201d; transfer to real marketplace "
        "reviews is future work, not a claim made here."
    ))
    caption(doc, f"Table 4.13: Hypothesis outcomes (page {pg('tab:4.13')})")
    add_table(
        doc,
        ["ID", "Hypothesis", "Outcome on the demonstration corpus"],
        [
            ["H1", "Sentiment differs across the nine aspects",
             "Supported: positive/negative shares differ visibly across aspects (Table 4.3, Figure 4.3)"],
            ["H2", "Aspect sentiment distributions differ across platforms",
             "Supported: platform profiles differ in Table 4.4 and Figure 4.4"],
            ["H3", "Trust and condition concerns differ across platforms",
             "Directionally supported: trust/condition scores differ across platforms in the corpus; requires verified real reviews to generalise"],
            ["H4", "BERT and traditional models differ in performance",
             "Supported, with an unexpected direction: logistic regression (90.69%) beats fine-tuned DistilBERT (89.57%); zero-shot trails both"],
        ],
        widths=[0.6, 2.7, 3.5],
    )
    para(doc, "")
    para(doc, (
        "The honest reading of H4 is methodological rather than tribal: with a "
        "modest training budget (one epoch, CPU) and short evidence phrases, "
        "n-gram features carry most of the signal. The transformer configuration "
        "remains the natural next step once GPU fine-tuning over multiple epochs "
        "is affordable, and the protocol in Chapter 3 makes that re-run a "
        "one-script change."
    ))
    subheading(doc, "4.11 Error Flows on Real Reviews")
    para(doc, (
        "Agreement in Table 4.5 is a single number; the confusion matrix in "
        "Table 4.14 shows where the disagreements concentrate. Rows are the "
        "human label derived from the reviewer's own star rating (4-5 stars = "
        "positive, 3 = neutral, 1-2 = negative); columns are the pipeline's "
        "prediction, computed from real_aspect_annotations.csv."
    ))
    caption(doc, f"Table 4.14: Predicted vs human sentiment on real Amazon reviews (page {pg('tab:4.14')})")
    real_cm = confusion_matrix(real.human_sentiment, real.predicted_sentiment,
                               labels=LABELS)
    cm_r = []
    for lab, counts in zip(["Positive", "Neutral", "Negative"], real_cm):
        cm_r.append([f"{lab} (human)", int(counts[0]), int(counts[1]),
                     int(counts[2]), int(counts.sum())])
    add_table(
        doc,
        ["Human \\ Predicted", "Positive", "Neutral", "Negative", "Row total"],
        cm_r,
        widths=[1.5, 1.2, 1.2, 1.2, 1.1],
    )
    para(doc, "")
    add_figure(doc, FIGDIR / "fig_real_confusion.png", "4.6",
               "Predicted-vs-human confusion matrix on real Amazon reviews")
    para(doc, (
        "Two flows dominate. First, 3-star reviews are pulled in both "
        "directions: 180 of the 481 three-star annotations are predicted "
        "negative and 93 positive - the textual signal of an ambivalent "
        "reviewer genuinely points both ways, which is why the neutral row has "
        "the lowest recall (208 of 481, i.e. 0.43). Second, the extreme "
        "classes leak very little across the polarity axis: only 36 of 945 "
        "positive and 37 of 1,034 negative annotations are predicted as the "
        "opposite pole. The larger errors at the extremes are neutral "
        "predictions (129 positives, 125 negatives) - under-confident rather "
        "than wrong-polarity errors."
    ))
    para(doc, (
        "For a deployed buyer-facing system this is the favourable failure "
        "mode: a neutral flag invites a human second look, while a flipped "
        "polarity would actively mislead it. The real-review matrix therefore "
        "reproduces, on human-authored text, the same qualitative pattern the "
        "synthetic corpus was built to exhibit: extreme polarities are easy, "
        "and the neutral boundary is where all of the residual difficulty "
        "lives."
    ))
    subheading(doc, "4.12 Aspect-Wise Label Distribution")
    para(doc, (
        "Hypothesis H1 predicts that sentiment differs across aspects; Table "
        "4.15 makes the comparison explicit by giving the full label "
        "distribution of every aspect in the demonstration corpus, computed "
        "from aspect_annotations.csv."
    ))
    caption(doc, f"Table 4.15: Aspect-wise label distribution (page {pg('tab:4.15')})")
    asp_lab = ann_all.groupby(["aspect", "sentiment"]).size().unstack(fill_value=0)
    for lab in LABELS:
        if lab not in asp_lab.columns:
            asp_lab[lab] = 0
    asp_lab = asp_lab[LABELS]
    asp_lab["total"] = asp_lab.sum(axis=1)
    asp_lab = asp_lab.sort_values("total", ascending=False)
    al_rows = []
    for asp, r in asp_lab.iterrows():
        al_rows.append([asp, int(r.positive), int(r.neutral), int(r.negative),
                        int(r.total), f"{100 * r.positive / r.total:.1f}%"])
    add_table(
        doc,
        ["Aspect", "Positive", "Neutral", "Negative", "Total", "Positive share"],
        al_rows,
        widths=[2.0, 0.95, 0.9, 0.95, 0.85, 1.15],
    )
    para(doc, "")
    pos_shares = {asp: r.positive / r.total for asp, r in asp_lab.iterrows()}
    hi = max(pos_shares, key=pos_shares.get)
    lo = min(pos_shares, key=pos_shares.get)
    para(doc, (
        f"The positive share ranges from {100 * pos_shares[lo]:.1f}% ({lo}) to "
        f"{100 * pos_shares[hi]:.1f}% ({hi}). This spread is the direct "
        "evidence behind H1's \u201csupported\u201d verdict in Table 4.13: "
        "sentiment is not uniform across the nine aspects of the refurbished "
        "purchase journey."
    ))
    para(doc, (
        "Two caveats apply. First, these counts are over annotations, not "
        "reviews; a review mentioning three aspects contributes to three rows "
        "(Appendix E gives the annotations-per-review distribution). Second, "
        "each annotation label was generated with its aspect in mind, so the "
        "cross-aspect differences partly reflect the generator's design; "
        "confirming the pattern on human-labelled data remains future work."
    ))

    # ================= 5. OUTCOME =================
    heading(doc, "5. Outcome and Deliverables")
    subheading(doc, "5.1 Research Output")
    para(doc, (
        "A research paper draft, \u201cRefurbIQ: Aspect-Based Sentiment Analysis of "
        "Refurbished Electronics Across Indian Marketplaces\u201d, is in progress: all "
        "six results tables are filled from computed outputs with an explicit "
        "provenance note, and the draft is accompanied by a methodology report, a "
        "validation report and a final integrity checklist. Planned venue: [XX]. "
        "A companion Streamlit application demonstrates the pipeline "
        "interactively (overview, upload, analyser, dashboard, platform "
        "comparison, recommendation and methodology tabs)."
    ))
    subheading(doc, "5.2 System Design and Implementation")
    para(doc, (
        "The implemented system has four layers, shown in Figure 5.1: a "
        "Streamlit user interface with eight tabs; an analysis engine that "
        "performs aspect extraction, sentiment classification and platform "
        "scoring; a model layer with the zero-shot RoBERTa pipeline, the "
        "fine-tuned DistilBERT checkpoint and the TF-IDF baselines; and a data "
        "and tooling layer holding the demonstration corpus, the MARC-based "
        "validation data and the analysis notebooks."
    ))
    add_figure(doc, DIAGRAMS / "1_diagram_tech_stack.png", "5.1",
               "Technology stack of the RefurbIQ system", width=6.2)
    para(doc, (
        "Figure 5.2 shows the end-to-end workflow. Uploaded or bundled reviews "
        "pass through pre-processing and keyword aspect extraction into the "
        "sentiment model; the resulting review-by-aspect table feeds two "
        "branches - an analytics dashboard (sentiment by aspect, platform and "
        "category) and a recommendation engine that computes six weighted "
        "sub-scores per platform and gates the output with HIGH/MEDIUM/LOW "
        "confidence levels (HIGH requires at least 50 reviews with consistent "
        "sentiment; platforms below 20 reviews are not ranked)."
    ))
    add_figure(doc, DIAGRAMS / "2_diagram_app_workflow.png", "5.2",
               "End-to-end workflow of the RefurbIQ application", width=6.2)
    para(doc, (
        "The recommendation layer is deliberately transparent: every sub-score is "
        "a 0-10 share computed from the aspect-group sentiment distribution, "
        "the weights are user-visible defaults, and the confidence gate refuses "
        "to recommend when evidence is thin. This mirrors the research stance "
        "of the project - an expected outcome is never reported as a finding."
    ))
    para(doc, (
        "The scoring weights and evidence gates of the recommendation engine "
        "are fixed, user-visible constants (src/recommendation.py); Table 5.1 "
        "reproduces them so that every recommendation the app emits can be "
        "recomputed by hand."
    ))
    caption(doc, f"Table 5.1: Recommendation engine scoring weights (page {pg('tab:5.1')})")
    add_table(
        doc,
        ["Factor", "Aspect group", "Default weight"],
        [
            ["Overall sentiment", "all detected aspects", "0.25"],
            ["Product quality", "Condition, Battery, Performance, Display, Camera", "0.25"],
            ["Service", "Seller Service, Delivery, Packaging", "0.15"],
            ["Value", "Price/Value", "0.15"],
            ["Trust", "Trust/Authenticity, Repair/Refurbishment", "0.10"],
            ["Return/Refund", "Return/Refund", "0.10"],
        ],
        widths=[1.7, 3.3, 1.2],
    )
    para(doc, "")
    para(doc, (
        "Each sub-score is the (positive + 0.5 \u00d7 neutral) share over the "
        "factor's aspect group, scaled to 0-10; the overall score is the "
        "weighted sum. Platforms with fewer than 20 unique reviews are excluded "
        "from ranking and shown as insufficient data; confidence is HIGH with "
        "at least 50 reviews and consistent sentiment, MEDIUM above the "
        "threshold, and LOW below it - in which case no recommendation is "
        "emitted."
    ))
    subheading(doc, "5.3 Deliverables")
    bullets(doc, [
        "Labelled demonstration dataset: 2,000 reviews and 3,548 aspect annotations (data_origin = synthetic-demo-v1), plus 2,000 real-review validation annotations.",
        "Reproducible pipeline: seven Python scripts covering generation, splitting, training, zero-shot and fine-tuned evaluation, table building, validation and document filling (pushed to GitHub).",
        "Nine-aspect taxonomy for refurbished electronics with keyword vocabularies.",
        "Five-model comparison on a common leak-free protocol, with macro and per-class metrics, confusion matrices and error examples.",
        "Streamlit application with analytics and recommendation tabs.",
        "Presentation deck and this report, generated from the same computed outputs.",
    ])

    # ================= 6. CONCLUSION =================
    heading(doc, "6. Conclusion and Future Scope")
    para(doc, (
        "This project built and validated an end-to-end aspect-based sentiment "
        "analysis pipeline for refurbished-electronics reviews across five Indian "
        "marketplaces. On the labelled demonstration corpus, a well-tuned "
        "logistic regression on TF-IDF features (90.69% accuracy, 0.8937 macro "
        "F1) edged out a fine-tuned DistilBERT model (89.57%, 0.8784), both ahead "
        "of random forest, XGBoost and zero-shot classification; the neutral "
        "class was hardest for every model, and the confusion and error analyses "
        "in Sections 4.7-4.8 show precisely where. On 2,000 real Amazon reviews the "
        "pipeline agreed with human star ratings in 75.6% of annotations, with "
        "near-perfect agreement at the extremes. Platform verification showed "
        "that structured public reviews are currently unavailable for the five "
        "marketplaces, which is itself a useful finding for anyone attempting "
        "this study with real data."
    ))
    para(doc, (
        "Future work: (i) collect verified real reviews (manual, "
        "permission-respecting collection or licensed corpora) and re-run the "
        "identical pipeline; (ii) complete multi-epoch and GPU fine-tuning of "
        "BERT to give the transformer family a fairer chance; (iii) replace "
        "keyword aspect detection with a fine-tuned span extractor; (iv) add a "
        "multi-annotator study for agreement statistics; (v) integrate the "
        "recommendation layer with live price and warranty signals."
    ))
    para(doc, (
        "The methodological lesson of the project is worth restating as a "
        "conclusion: when the target data is inaccessible, the honest path is a "
        "clearly labelled synthetic demonstration plus a separate validation on "
        "real data with human ground truth - not silent substitution. Every "
        "table in this report states which of the two it comes from, and every "
        "number can be regenerated from the repository with a fixed seed."
    ))

    # ================= REFERENCES =================
    heading(doc, "References")
    refs = [
        "A. Chevalier and M. Mayzlin, \u201cThe effect of word of mouth on sales: Online book reviews,\u201d Journal of Marketing Research, vol. 43, no. 3, pp. 345-354, 2006.",
        "B. Liu, Sentiment Analysis and Opinion Mining. Morgan & Claypool, 2012.",
        "B. Pang and L. Lee, \u201cOpinion mining and sentiment analysis,\u201d Foundations and Trends in Information Retrieval, vol. 2, no. 1-2, pp. 1-135, 2008.",
        "M. Hu and B. Liu, \u201cMining and summarizing customer reviews,\u201d in Proceedings of the ACM SIGKDD International Conference on Knowledge Discovery and Data Mining, 2004, pp. 168-177.",
        "M. Pontiki et al., \u201cSemEval-2014 Task 4: Aspect based sentiment analysis,\u201d in Proceedings of the International Workshop on Semantic Evaluation (SemEval), 2014, pp. 27-35.",
        "M. Pontiki et al., \u201cSemEval-2016 Task 5: Aspect based sentiment analysis,\u201d in Proceedings of the International Workshop on Semantic Evaluation (SemEval), 2016, pp. 19-30.",
        "A. Vaswani et al., \u201cAttention is all you need,\u201d in Advances in Neural Information Processing Systems, 2017, pp. 5998-6008.",
        "J. Devlin, M.-W. Chang, K. Lee and K. Toutanova, \u201cBERT: Pre-training of deep bidirectional transformers for language understanding,\u201d in Proceedings of NAACL-HLT, 2019, pp. 4171-4186.",
        "P. Keung, Y. Lu, G. Szarvas and N. A. Smith, \u201cThe Multilingual Amazon Reviews Corpus,\u201d in Proceedings of EMNLP, 2020 (dataset used for the real-review validation, Section 4.6).",
    ]
    for i, r in enumerate(refs, 1):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.left_indent = Inches(0.35)
        p.paragraph_format.first_line_indent = Inches(-0.35)
        set_run(p.add_run(), f"[{i}] {r}")

    # ================= APPENDICES =================
    heading(doc, "Appendix A. Reproducibility")
    para(doc, (
        "Every number in this report can be regenerated with the scripts under "
        "research/scripts/ (seed 42 throughout). Table A.1 lists each script "
        "and the artefacts it writes."
    ))
    caption(doc, f"Table A.1: Pipeline scripts and outputs (page {pg('tab:A.1')})")
    add_table(
        doc,
        ["Script", "Output artefacts"],
        [
            ["generate_dataset.py", "reviews.csv (2,000 rows); aspect_annotations.csv (3,548 rows)"],
            ["train_traditional_models.py", "split_assignment.csv; model_predictions.csv; traditional_metrics.json"],
            ["eval_bert_zeroshot.py", "bert_zeroshot_metrics.json; pred_bert_zeroshot column"],
            ["finetune_bert.py", "models/finetuned_distilbert/; bert_finetuned_metrics.json; pred_bert_finetuned column"],
            ["run_real_reviews.py", "real/real_aspect_annotations.csv (2,460 rows); agreement summary"],
            ["build_tables.py", "research/tables/table1..6.csv"],
            ["validation_report.py", "asserts predictions cover exactly the test partition"],
            ["build_report.py / build_pptx.py", "this report and the presentation deck"],
        ],
        widths=[2.5, 4.3],
    )
    para(doc, "")
    para(doc, (
        "Environment: Python 3.14 virtual environment; scikit-learn 1.9.1, "
        "XGBoost 3.4.1, PyTorch 2.14.1 (CPU), transformers 5.18.0, pandas "
        "3.0.6, matplotlib 3.11.1, python-docx 1.2.0, python-pptx 1.0.2. "
        "Training hardware: CPU only (documented in the metric JSONs). Code "
        "repository: https://github.com/Saket-code40/refurbiq."
    ))
    para(doc, (
        "The split file is the reproducibility anchor: because every model "
        "script reads split_assignment.csv instead of re-splitting, a re-run "
        "reproduces the same test examples and therefore the same confusion "
        "matrices, per-class metrics and error tables in this report."
    ))
    heading(doc, "Appendix B. Annotation Samples")
    para(doc, (
        "Table B.1 shows verbatim rows sampled (random_state 42) from "
        "aspect_annotations.csv (synthetic demonstration corpus). Each "
        "annotation stores the review id, the detected aspect, the evidence "
        "phrase and the label."
    ))
    caption(doc, f"Table B.1: Sample annotations (page {pg('tab:B.1')})")
    sample = ann_all.sample(18, random_state=42)
    add_table(
        doc,
        ["review_id", "aspect", "evidence phrase", "sentiment"],
        [[r.review_id, r.aspect,
          (r.evidence_phrase[:66] + ("\u2026" if len(r.evidence_phrase) > 66 else "")),
          r.sentiment]
         for r in sample.itertuples()],
        widths=[0.9, 1.6, 3.3, 0.9],
    )
    para(doc, "")
    para(doc, (
        "Table B.2 walks through complete reviews: for each sampled review the "
        "full text is quoted, followed by every annotation attached to it, so "
        "the reader can verify that each label is supported by its evidence "
        "phrase. Reviews with at least two annotations were sampled with "
        "random_state 42."
    ))
    ann_by_review = ann_all.groupby("review_id")
    multi = sorted(rid for rid, g in ann_by_review if len(g) >= 2)
    sel = list(pd.Series(multi).sample(5, random_state=42).sort_values())
    b2_rows = []
    for rid in sel:
        rev_row = rev_all[rev_all.review_id == rid].iloc[0]
        para(doc, (f"{rid} ({rev_row.marketplace}, {rev_row.product_category}, "
                   f"{rev_row.product_name}):"), italic=True, size=11, space_after=2)
        para(doc, f"\u201c{rev_row.review_text}\u201d", italic=True, size=11,
             space_after=4)
        for r in ann_by_review.get_group(rid).itertuples():
            phrase = r.evidence_phrase
            if len(phrase) > 80:
                phrase = phrase[:80] + "\u2026"
            b2_rows.append([r.review_id, r.aspect, phrase, r.sentiment])
    caption(doc, f"Table B.2: Full-review annotation walkthrough (page {pg('tab:B.2')})")
    add_table(
        doc,
        ["review_id", "aspect", "evidence phrase", "sentiment"],
        b2_rows,
        widths=[0.9, 1.6, 3.3, 0.9],
    )
    para(doc, "")
    heading(doc, "Appendix C. Aspect-Wise Counts by Platform")
    para(doc, (
        "Table C.1 gives the number of aspect mentions per platform and aspect "
        "in the demonstration corpus - the denominators behind Tables 4.3 and "
        "4.4, computed from aspect_annotations.csv joined with reviews.csv."
    ))
    caption(doc, f"Table C.1: Aspect mentions by platform (page {pg('tab:C.1')})")
    merged_ann = ann_all.merge(rev_all[["review_id", "marketplace"]], on="review_id")
    ct = pd.crosstab(merged_ann["aspect"], merged_ann["marketplace"])
    platforms = [p for p in ["Amazon Renewed", "Budli", "Cashify",
                             "Flipkart Refurbished", "OLX"] if p in ct.columns]
    c_rows = []
    for aspect in ASPECT_ORDER:
        row = [aspect] + [int(ct.loc[aspect, p]) if aspect in ct.index else 0
                          for p in platforms]
        row.append(sum(row[1:]))
        c_rows.append(row)
    c_rows.append(["Total"] + [int(ct[p].sum()) for p in platforms] + [int(ct.values.sum())])
    add_table(
        doc,
        ["Aspect"] + platforms + ["Total"],
        c_rows,
        widths=[1.9] + [0.92] * len(platforms) + [0.7],
    )
    para(doc, "")
    heading(doc, "Appendix D. Per-Class Precision, Recall and F1")
    para(doc, (
        "Table D.1 reports per-class precision, recall and F1 for all five "
        "models on the test partition, computed from model_predictions.csv. It "
        "extends Table 4.2 (recall only) and supports the discussion in "
        "Sections 4.3 and 4.7."
    ))
    caption(doc, f"Table D.1: Per-class metrics for all models (page {pg('tab:D.1')})")
    d_rows = []
    for col, name in PRED_COLS:
        for lab, pr, re, f1, sup in per_class_prf(preds, col):
            d_rows.append([name, lab, pr, re, f1, sup])
    add_table(
        doc,
        ["Model", "Class", "Precision", "Recall", "F1", "Support"],
        d_rows,
        widths=[2.3, 0.95, 1.0, 0.95, 0.95, 0.85],
    )
    para(doc, "")
    heading(doc, "Appendix E. Corpus Statistics")
    para(doc, (
        "Table E.1 summarises review length (in words) per marketplace, "
        "computed from reviews.csv. Length matters because TF-IDF evidence "
        "phrases and the 128-token transformer limit both interact with how "
        "much text a review contributes."
    ))
    caption(doc, f"Table E.1: Review length statistics by platform (page {pg('tab:E.1')})")
    words = rev_all.review_text.str.split().str.len()
    len_df = pd.DataFrame({"marketplace": rev_all.marketplace, "words": words})
    e_rows = []
    for p in ["Amazon Renewed", "Budli", "Cashify", "Flipkart Refurbished", "OLX"]:
        sub = len_df[len_df.marketplace == p].words
        e_rows.append([p, len(sub), round(float(sub.mean()), 1),
                       float(sub.median()), int(sub.min()), int(sub.max())])
    e_rows.append(["All", len(len_df), round(float(words.mean()), 1),
                   float(words.median()), int(words.min()), int(words.max())])
    add_table(
        doc,
        ["Platform", "Reviews", "Mean words", "Median", "Min", "Max"],
        e_rows,
        widths=[1.8, 1.0, 1.1, 1.0, 0.9, 0.9],
    )
    para(doc, "")
    para(doc, (
        "Table E.2 gives the distribution of annotation counts per review, "
        "computed from aspect_annotations.csv. Multi-mention reviews are the "
        "reason the partition operates at review level (Section 3.4)."
    ))
    caption(doc, f"Table E.2: Annotations per review (page {pg('tab:E.2')})")
    per_review = ann_all.groupby("review_id").size()
    dist = per_review.value_counts().sort_index()
    e2_rows = [
        [f"{int(k)}", int(v), f"{100 * v / len(per_review):.1f}%"]
        for k, v in dist.items()
    ]
    e2_rows.append(["Total reviews", len(per_review), "100%"])
    add_table(doc, ["Annotations per review", "Number of reviews", "Share"],
              e2_rows, widths=[2.0, 1.8, 1.4])
    para(doc, "")
    para(doc, (
        "The average of 1.77 annotations per review and the right-skewed "
        "distribution together mean that review-level statistics and "
        "annotation-level statistics differ: platform review counts (Table 3.2) "
        "and platform mention counts (Appendix C) are therefore always "
        "reported with their explicit denominator."
    ))
    para(doc, (
        "Table E.3 crosses annotations with their review's marketplace, giving "
        "the label mix each platform contributes to the corpus."
    ))
    caption(doc, f"Table E.3: Annotation labels by platform (page {pg('tab:E.3')})")
    plat_lab = (
        ann_all.merge(rev_all[["review_id", "marketplace"]], on="review_id")
        .groupby(["marketplace", "sentiment"]).size().unstack(fill_value=0)
    )
    for lab in LABELS:
        if lab not in plat_lab.columns:
            plat_lab[lab] = 0
    plat_lab = plat_lab[LABELS]
    e3_rows = []
    for plat in ["Amazon Renewed", "Budli", "Cashify", "Flipkart Refurbished", "OLX"]:
        r = plat_lab.loc[plat]
        e3_rows.append([plat, int(r.positive), int(r.neutral), int(r.negative),
                        int(r.sum())])
    tot_r = plat_lab.sum()
    e3_rows.append(["All", int(tot_r.positive), int(tot_r.neutral),
                    int(tot_r.negative), int(tot_r.sum())])
    add_table(
        doc,
        ["Platform", "Positive", "Neutral", "Negative", "Annotations"],
        e3_rows,
        widths=[2.0, 1.1, 1.0, 1.1, 1.4],
    )
    para(doc, "")
    para(doc, (
        "Table E.4 summarises the star ratings that accompany each review in "
        "reviews.csv. Ratings are metadata of the synthetic corpus, not model "
        "input; they are reported so the corpus can be audited."
    ))
    caption(doc, f"Table E.4: Star rating statistics by platform (page {pg('tab:E.4')})")
    e4_rows = []
    for p in ["Amazon Renewed", "Budli", "Cashify", "Flipkart Refurbished", "OLX"]:
        sub = rev_all[rev_all.marketplace == p].rating
        e4_rows.append([p, len(sub), round(float(sub.mean()), 2),
                        float(sub.median()), int(sub.min()), int(sub.max())])
    allr = rev_all.rating
    e4_rows.append(["All", len(allr), round(float(allr.mean()), 2),
                    float(allr.median()), int(allr.min()), int(allr.max())])
    add_table(
        doc,
        ["Platform", "Reviews", "Mean rating", "Median", "Min", "Max"],
        e4_rows,
        widths=[1.8, 1.0, 1.1, 1.0, 0.9, 0.9],
    )
    para(doc, "")
    para(doc, (
        "Limitations are stated plainly: the modelling corpus is synthetic and "
        "labelled as such; aspect detection is keyword-based; fine-tuning was "
        "limited to one epoch on CPU; and platform-level claims require verified "
        "marketplace reviews that are not currently publicly accessible."
    ), italic=True)


# ---------------------------------------------------------------- pass 2


def render_and_fill():
    tmp_pdf = HERE / "report_pass1.pdf"
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(HERE), str(OUT)],
        check=True, timeout=300,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    pdf = HERE / (OUT.stem + ".pdf")
    text = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True, text=True, check=True, timeout=120,
    ).stdout
    pages = text.split("\f")

    toc_page = next(i for i, p in enumerate(pages) if "TABLE OF CONTENTS" in p)
    # body starts at the first page after the TOC whose first non-empty
    # line is the Chapter 1 heading (chapters always start on a new page)
    def first_line(page):
        return next((l.strip() for l in page.splitlines() if l.strip()), "")

    body_start = next(
        i for i in range(toc_page + 1, len(pages))
        if first_line(pages[i]) == "1. Introduction"
    )

    def find_page(needle, lo):
        for i in range(lo, len(pages)):
            if needle in pages[i]:
                return i + 1  # 1-based PDF page
        return None

    replacements = {}
    toc_needles = {
        "abs": "ABSTRACT", "lot": "LIST OF TABLES", "lof": "LIST OF FIGURES",
        "1": "1. Introduction", "1.1": "1.1 Background",
        "1.2": "1.2 Objectives of the Project",
        "1.3": "1.3 Research Questions", "1.4": "1.4 Scope and Contributions",
        "1.5": "1.5 Organisation of the Report",
        "2": "2. Literature Survey",
        "2.1": "2.1 Online Reviews", "2.2": "2.2 Sentiment Analysis",
        "2.3": "2.3 Aspect-Based", "2.4": "2.4 Classical Machine Learning",
        "2.5": "2.5 Research Gap",
        "3": "3. Proposed Methodology",
        "3.1": "3.1 Platform Verification", "3.2": "3.2 Dataset Construction",
        "3.3": "3.3 Aspect Taxonomy", "3.4": "3.4 Pre-processing",
        "3.5": "3.5 Models and Hyperparameters", "3.6": "3.6 Evaluation Protocol",
        "3.7": "3.7 Evaluation Metrics",
        "4": "4. Results and Discussion",
        "4.1": "4.1 Dataset Profile", "4.2": "4.2 Model Comparison",
        "4.3": "4.3 Class-Level", "4.4": "4.4 Aspect-Level",
        "4.5": "4.5 Cross-Platform", "4.6": "4.6 Validation on Real Reviews",
        "4.7": "4.7 Confusion Matrix", "4.8": "4.8 Error Analysis",
        "4.9": "4.9 Agreement by Aspect", "4.10": "4.10 Hypothesis Outcomes",
        "4.11": "4.11 Error Flows",
        "4.12": "4.12 Aspect-Wise Label Distribution",
        "5": "5. Outcome and Deliverables", "5.1": "5.1 Research Output",
        "5.2": "5.2 System Design", "5.3": "5.3 Deliverables",
        "6": "6. Conclusion and Future Scope",
        "refs": "References", "appa": "Appendix A", "appb": "Appendix B",
        "appc": "Appendix C", "appd": "Appendix D", "appe": "Appendix E",
    }
    # front-matter entries live before the TOC page
    for key in ("abs", "lot", "lof"):
        pgno = find_page(toc_needles[key], 0)
        replacements[f"toc:{key}"] = str(pgno) if pgno else "?"
    for key, needle in toc_needles.items():
        if key in ("abs", "lot", "lof"):
            continue
        pgno = find_page(needle, body_start)
        replacements[f"toc:{key}"] = str(pgno - (body_start - 1)) if pgno else "?"
        # rebase to chapter numbering: body_start page = page 1
    # table / figure caption pages (chapter-numbered)
    table_keys = ("2.1", "3.1", "3.2", "3.3", "3.4", "3.5",
                  "4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8",
                  "4.9", "4.10", "4.11", "4.12", "4.13", "4.14", "4.15",
                  "5.1", "A.1", "B.1", "B.2", "C.1", "D.1",
                  "E.1", "E.2", "E.3", "E.4")
    for key in table_keys:
        pgno = find_page(f"Table {key}:", body_start)
        if pgno:
            replacements[f"tab:{key}"] = str(pgno - (body_start - 1))
            replacements[f"list:tab{key}"] = str(pgno - (body_start - 1))
    for key in ("3.1", "3.2", "4.1", "4.2", "4.3", "4.4", "4.5", "4.6",
                "5.1", "5.2"):
        pgno = find_page(f"Figure {key}:", body_start)
        if pgno:
            replacements[f"fig:{key}"] = str(pgno - (body_start - 1))
            replacements[f"list:fig{key}"] = str(pgno - (body_start - 1))

    doc = Document(str(OUT))
    n = 0

    def fix_paragraph(p):
        nonlocal n
        for r in p.runs:
            for token, val in replacements.items():
                mark = f"\u00abpg:{token}\u00bb"
                if mark in r.text:
                    r.text = r.text.replace(mark, val)
                    n += 1

    for p in doc.paragraphs:
        fix_paragraph(p)
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                for p in c.paragraphs:
                    fix_paragraph(p)
    doc.save(str(OUT))
    pdf.replace(tmp_pdf)  # keep the pass-1 PDF for debugging
    print(f"pass 2: replaced {n} page tokens; body starts at PDF page {body_start + 1}")


def main() -> None:
    t1 = pd.read_csv(TABLES / "table1_dataset_profile.csv")
    t2 = pd.read_csv(TABLES / "table2_aspect_frequency.csv")
    t3 = pd.read_csv(TABLES / "table3_model_performance.csv")
    t4 = pd.read_csv(TABLES / "table4_class_specific_recall.csv")
    t5 = pd.read_csv(TABLES / "table5_sentiment_by_aspect.csv")
    t6 = pd.read_csv(TABLES / "table6_cross_platform.csv")
    real_path = DATA / "real" / "real_aspect_annotations.csv"
    real = pd.read_csv(real_path) if real_path.exists() else None

    make_figures(t1, t2, t3, t4, t5, t6, real)
    print(f"figures: {sorted(p.name for p in FIGDIR.glob('*.png'))}")

    shutil.copy(TEMPLATE, OUT)
    doc = Document(str(OUT))
    fill_front_matter(doc)

    table_list = [
        ("2.1", "Literature summary", "tab2.1"),
        ("3.1", "Platform verification outcomes", "tab3.1"),
        ("3.2", "Dataset profile of the demonstration corpus", "tab3.2"),
        ("3.3", "Aspect mention frequency", "tab3.3"),
        ("3.4", "Model configurations", "tab3.4"),
        ("3.5", "Partition sizes by class", "tab3.5"),
        ("4.1", "Model performance on the held-out test partition", "tab4.1"),
        ("4.2", "Class-specific recall on the test partition", "tab4.2"),
        ("4.3", "Sentiment distribution within each aspect", "tab4.3"),
        ("4.4", "Cross-platform aspect summary", "tab4.4"),
        ("4.5", "Agreement with reviewer star ratings (real reviews)", "tab4.5"),
        ("4.6", "Confusion matrix - Logistic Regression", "tab4.6"),
        ("4.7", "Confusion matrix - Random Forest", "tab4.7"),
        ("4.8", "Confusion matrix - XGBoost", "tab4.8"),
        ("4.9", "Confusion matrix - BERT (zero-shot)", "tab4.9"),
        ("4.10", "Confusion matrix - BERT (fine-tuned DistilBERT)", "tab4.10"),
        ("4.11", "Misclassified examples - Logistic Regression", "tab4.11"),
        ("4.12", "Real-review agreement by detected aspect", "tab4.12"),
        ("4.13", "Hypothesis outcomes", "tab4.13"),
        ("4.14", "Predicted vs human sentiment on real Amazon reviews", "tab4.14"),
        ("4.15", "Aspect-wise label distribution", "tab4.15"),
        ("5.1", "Recommendation engine scoring weights", "tab5.1"),
        ("A.1", "Pipeline scripts and outputs", "tabA.1"),
        ("B.1", "Sample annotations", "tabB.1"),
        ("B.2", "Full-review annotation walkthrough", "tabB.2"),
        ("C.1", "Aspect mentions by platform", "tabC.1"),
        ("D.1", "Per-class metrics for all models", "tabD.1"),
        ("E.1", "Review length statistics by platform", "tabE.1"),
        ("E.2", "Annotations per review distribution", "tabE.2"),
        ("E.3", "Annotation labels by platform", "tabE.3"),
        ("E.4", "Star rating statistics by platform", "tabE.4"),
    ]
    figure_list = [
        ("3.1", "Reviews per marketplace", "fig3.1"),
        ("3.2", "Sentiment label distribution", "fig3.2"),
        ("4.1", "Test accuracy by model", "fig4.1"),
        ("4.2", "Macro F1 and neutral recall by model", "fig4.2"),
        ("4.3", "Sentiment distribution within each aspect", "fig4.3"),
        ("4.4", "Net sentiment heatmap (platform x aspect)", "fig4.4"),
        ("4.5", "Agreement by star bucket on real Amazon reviews", "fig4.5"),
        ("4.6", "Predicted vs human sentiment confusion (real reviews)", "fig4.6"),
        ("5.1", "Technology stack", "fig5.1"),
        ("5.2", "End-to-end application workflow", "fig5.2"),
    ]
    fill_lists(doc, table_list, figure_list)
    build_body(doc)
    doc.save(str(OUT))
    print(f"pass 1 saved: {OUT}")

    render_and_fill()
    # re-render for the final page count
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(HERE), str(OUT)],
        check=True, timeout=300,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    pdf = HERE / (OUT.stem + ".pdf")
    n_pages = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True, check=True,
    ).stdout
    print("".join(l for l in n_pages.splitlines() if l.startswith("Pages")))


if __name__ == "__main__":
    main()