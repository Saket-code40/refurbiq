"""Build RefurbIQ_PBL3.pptx from the Plant Disease template.

Strategy: open the reference deck, replace ONLY text/chart/table content
in the existing shapes (matched by shape name), and keep every fill,
font, shadow, banner, master and logo untouched. The slide-2 outline
SmartArt is edited at the XML level after save.

Integrity rules honored:
- Data values come from research/data/* (computed outputs of the
  synthetic-demo-v1 pipeline) - nothing invented.
- User-specific fields left blank in the brief stay visible as [XX]
  style placeholders: registration no., department, course code,
  guide names, date, literature-survey count, planned venue.
- The model called "BERT" in the deck is the actually fine-tuned
  checkpoint (distilbert-base-uncased, 1 epoch, CPU); the real
  configuration is stated on slides 11/13.

Usage:
    python build_pptx.py
"""

from __future__ import annotations

import copy
import math
import re
import shutil
import zipfile
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
TEMPLATE = Path.home() / "Downloads" / "Plant_Disease_Detection_PBL3.pptx"
OUT = HERE / "RefurbIQ_PBL3.pptx"

NAVY = RGBColor(0x1F, 0x38, 0x64)
GREY = RGBColor(0x55, 0x65, 0x75)
TEAL = RGBColor(0x1F, 0x6F, 0x78)

# ---------------------------------------------------------------- helpers


def rewrite_txbody(txBody, blocks) -> None:
    """Replace a text body's paragraphs, cloning paragraph/run formats.

    blocks: list of str  -> one run per paragraph
            list of [(text, bold, italic), ...] -> multi-run paragraph
    Formatting (font, size, colour, bullets, alignment) is cloned from
    the paragraph at the same index of the original text body.
    """
    paras = txBody.findall(qn("a:p"))
    tmpl = []
    for p in paras:
        pPr = p.find(qn("a:pPr"))
        r = p.find(qn("a:r"))
        rPr = r.find(qn("a:rPr")) if r is not None else None
        tmpl.append(
            (
                copy.deepcopy(pPr) if pPr is not None else None,
                copy.deepcopy(rPr) if rPr is not None else None,
            )
        )
    for p in paras:
        txBody.remove(p)
    for i, block in enumerate(blocks):
        pPr_t, rPr_t = tmpl[min(i, len(tmpl) - 1)] if tmpl else (None, None)
        p = txBody.makeelement(qn("a:p"), {})
        if pPr_t is not None:
            p.append(copy.deepcopy(pPr_t))
        segs = block if isinstance(block, list) else [(block, None, None)]
        for text, bold, italic in segs:
            r = p.makeelement(qn("a:r"), {})
            if rPr_t is not None:
                rPr = copy.deepcopy(rPr_t)
            else:
                rPr = p.makeelement(qn("a:rPr"), {"lang": "en-IN"})
            if bold is not None:
                rPr.set("b", "1" if bold else "0")
            if italic is not None:
                rPr.set("i", "1" if italic else "0")
            r.append(rPr)
            t = r.makeelement(qn("a:t"), {})
            t.text = text
            r.append(t)
            p.append(r)
        txBody.append(p)


def rewrite_tf(shape, blocks) -> None:
    rewrite_txbody(shape.text_frame._txBody, blocks)


def set_cell(cell, blocks) -> None:
    if isinstance(blocks, str):
        blocks = [blocks]
    rewrite_txbody(cell.text_frame._txBody, blocks)


def by_name(slide) -> dict:
    return {sh.name: sh for sh in slide.shapes}


def set_chart(shape, categories, series_name, values, title=None) -> None:
    data = CategoryChartData()
    data.categories = categories
    data.add_series(series_name, values)
    chart = shape.chart
    chart.replace_data(data)
    # replace_data() leaves the template's <c:title> untouched; rewrite it
    # so no template wording survives in the chart.
    if title is not None and chart.has_title:
        rewrite_txbody(chart.chart_title.text_frame._txBody, [title])


def set_notes(slide, text: str) -> None:
    slide.notes_slide.notes_text_frame.text = text


# ---------------------------------------------------------------- build


def main() -> None:
    shutil.copy(TEMPLATE, OUT)
    prs = Presentation(str(OUT))
    S = prs.slides

    # ================= SLIDE 1 - Title =================
    s = S[0]
    sh = by_name(s)
    # University lines: keep the 31/24/24 bold Times sizes of the template.
    title_tf = sh["Title 1"].text_frame
    txBody = title_tf._txBody
    paras = txBody.findall(qn("a:p"))
    uni_lines = [
        "Manipal University Jaipur",
        "School of Business and Commerce",
        "[Department]",
    ]
    tmpl = []
    for p in paras:
        pPr = p.find(qn("a:pPr"))
        r = p.find(qn("a:r"))
        rPr = r.find(qn("a:rPr")) if r is not None else None
        tmpl.append(
            (
                copy.deepcopy(pPr) if pPr is not None else None,
                copy.deepcopy(rPr) if rPr is not None else None,
            )
        )
    for p in paras:
        txBody.remove(p)
    for i, line in enumerate(uni_lines):
        pPr_t, rPr_t = tmpl[min(i, len(tmpl) - 1)]
        p = txBody.makeelement(qn("a:p"), {})
        if pPr_t is not None:
            p.append(copy.deepcopy(pPr_t))
        r = p.makeelement(qn("a:r"), {})
        r.append(copy.deepcopy(rPr_t) if rPr_t is not None else p.makeelement(qn("a:rPr"), {}))
        t = r.makeelement(qn("a:t"), {})
        t.text = line
        r.append(t)
        p.append(r)
        txBody.append(p)

    rewrite_tf(
        sh["Rectangle 4"],
        ["[COURSE CODE] Project Based Learning Presentation", "On", " "],
    )
    # Title + subtitle banner: template is one 24pt line; ours is longer,
    # so two paragraphs (title 14pt bold, subtitle 11pt italic) and a
    # slightly taller banner (still above the presenter table at 5.14in).
    banner = sh["Rectangle 8"]
    banner.height = Inches(0.78)
    rewrite_tf(
        banner,
        [
            [(
                "RefurbIQ: Aspect-Based Sentiment Analysis of Refurbished "
                "Electronics Across Indian Marketplaces",
                True,
                None,
            )],
            [(
                "A Comparative Evaluation of Traditional Machine Learning and BERT",
                None,
                True,
            )],
        ],
    )
    for p, size, italic in (
        (banner.text_frame.paragraphs[0], 14, False),
        (banner.text_frame.paragraphs[1], 11, True),
    ):
        p.alignment = PP_ALIGN.CENTER
        for r in p.runs:
            r.font.size = Pt(size)
            r.font.bold = not italic
            r.font.italic = italic

    # Presenter / guidance table
    table = next(x for x in s.shapes if x.has_table).table
    set_cell(
        table.rows[0].cells[0],
        ["Presented by", "Saket Sharma ([REG NO])"],
    )
    set_cell(
        table.rows[0].cells[2],
        ["Under the Guidance of", "[Guide name(s)]"],
    )
    rewrite_tf(sh["Date Placeholder 4"], ["[DD/MM/YYYY]"])
    set_notes(
        s,
        "Good morning. I am Saket Sharma, presenting my Project Based "
        "Learning work, RefurbIQ, which analyses sentiment in refurbished "
        "electronics reviews at aspect level across five Indian "
        "marketplaces. Registration number, course code, guide names and "
        "date are visible placeholders to be filled before submission.",
    )

    # ================= SLIDE 2 - Outline (SmartArt edited post-save) ====
    set_notes(
        S[1],
        "The talk follows this outline: abstract and introduction, then "
        "motivation, objective and literature survey, the research gap and "
        "problem statement, methodology, results and discussion, and the "
        "outcome.",
    )

    # ================= SLIDE 3 - Abstract =================
    s = S[2]
    sh = by_name(s)
    rewrite_tf(
        sh["Abstract points"],
        [
            "Analyses refurbished electronics reviews in India at aspect level: nine aspects, three polarity labels.",
            "Compares five marketplaces: Cashify, Amazon Renewed, Flipkart Refurbished, OLX and Budli under one taxonomy.",
            "Compares Logistic Regression, Random Forest and XGBoost (TF-IDF) with fine-tuned BERT on the same split.",
            "Best accuracy 90.7% (Logistic Regression); the neutral class is hardest for every model.",
            "Corpus: 2,000 synthetic demo reviews (seed 42), built to validate the pipeline end to end.",
        ],
    )
    rewrite_tf(sh["Stat value 1"], ["2,000"])
    rewrite_tf(sh["Stat label 1"], ["reviews collected (synthetic demo)"])
    rewrite_tf(sh["Stat value 2"], ["5"])
    rewrite_tf(sh["Stat label 2"], ["platforms compared"])
    rewrite_tf(sh["Stat value 3"], ["90.7%"])
    rewrite_tf(sh["Stat label 3"], ["best model accuracy (Log. Reg.)"])
    rewrite_tf(
        sh["Abstract takeaway text"],
        [
            "A single overall rating hides which aspect causes dissatisfaction; "
            "aspect-level analysis shows whether the problem is battery, trust, "
            "returns or price.",
        ],
    )
    set_notes(
        s,
        "RefurbIQ reads reviews at aspect level instead of one overall "
        "rating, compares five Indian platforms, and benchmarks four models "
        "on the same split. The corpus is a clearly labelled synthetic demo "
        "of 2,000 reviews used to validate the full pipeline before real "
        "marketplace reviews are collected.",
    )

    # ================= SLIDE 4 - Introduction =================
    s = S[3]
    sh = by_name(s)
    # Replace the photo with a labelled placeholder frame (spec allows it).
    pic = sh["Euphorbia Milli sample photo"]
    pic._element.getparent().remove(pic._element)
    frame = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.40), Inches(1.35), Inches(3.30), Inches(3.30)
    )
    frame.fill.solid()
    frame.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    frame.line.color.rgb = NAVY
    frame.line.width = Pt(1.25)
    tf = frame.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = "insert photo: laptop, phone and DSLR"
    r.font.name = "Times New Roman"
    r.font.size = Pt(14)
    r.font.italic = True
    r.font.color.rgb = GREY
    rewrite_tf(sh["Photo caption"], ["Refurbished phone, laptop, DSLR"])
    rewrite_tf(
        sh["Scope text"],
        [
            "Scope",
            "Phones, laptops, DSLR; nine aspects, three labels.",
        ],
    )
    rewrite_tf(
        sh["Intro points"],
        [
            [
                ("Why it matters: ", True, None),
                ("India's refurbished market is growing, but buyers face uncertainty about condition and authenticity.", None, None),
            ],
            [
                ("Current practice: ", True, None),
                ("one star rating per review hides which aspect caused dissatisfaction.", None, None),
            ],
            [
                ("ABSA: ", True, None),
                ("attaches a sentiment to each aspect - battery, condition, seller service, trust.", None, None),
            ],
            [
                ("BERT vs TF-IDF: ", True, None),
                ("contextual transformer features against classical n-gram features, on the same split.", None, None),
            ],
            [
                ("Indian platforms: ", True, None),
                ("Cashify, Amazon Renewed, Flipkart Refurbished, OLX and Budli under one aspect taxonomy.", None, None),
            ],
        ],
    )
    set_notes(
        s,
        "Refurbished devices are cheaper, but buyers cannot verify battery "
        "health, condition or authenticity before paying. Star ratings hide "
        "the cause of dissatisfaction, which is why we use aspect-based "
        "sentiment analysis and compare classical TF-IDF models with BERT.",
    )

    # ================= SLIDE 5 - Motivation =================
    s = S[4]
    sh = by_name(s)
    cards = [
        (
            "Buyer uncertainty",
            "Buyers cannot verify condition, battery health or authenticity of a "
            "refurbished device before paying.",
        ),
        (
            "One label hides why",
            "A 3-star review may praise the battery but blame the seller; a single "
            "sentiment label loses this information.",
        ),
        (
            "Platform gaps unknown",
            "Whether Cashify, Amazon Renewed, Flipkart, OLX or Budli differ by "
            "aspect has not been measured.",
        ),
        (
            "Little prior work",
            "ABSA research mostly covers new products and Western marketplaces; "
            "Indian refurbished platforms are barely studied.",
        ),
    ]
    for i, (head, text) in enumerate(cards, 1):
        rewrite_tf(sh[f"Motivation head {i}"], [head])
        rewrite_tf(sh[f"Motivation text {i}"], [text])
    set_notes(
        s,
        "Four motivations: buyer uncertainty, single-label ratings hiding "
        "the cause, unknown platform differences, and very little prior "
        "work on Indian refurbished reviews.",
    )

    # ================= SLIDE 6 - Objective =================
    s = S[5]
    sh = by_name(s)
    objs = [
        (
            "Aspect taxonomy",
            "Define nine aspects for refurbished electronics and tag every mention",
        ),
        (
            "Cross-platform comparison",
            "Measure how aspect sentiment differs across the five platforms",
        ),
        (
            "Model comparison",
            "Evaluate LR, RF, XGBoost and fine-tuned BERT on the same split",
        ),
        (
            "Insights",
            "Report which aspects and platforms drive satisfaction and distrust",
        ),
    ]
    for i, (head, text) in enumerate(objs, 1):
        rewrite_tf(sh[f"Objective head {i}"], [head])
        rewrite_tf(sh[f"Objective text {i}"], [text])
    rewrite_tf(sh["Aims head"], ["The study aims to"])
    rewrite_tf(
        sh["Aims points"],
        [
            "Answer RQ1: which aspects drive satisfaction and dissatisfaction",
            "Answer RQ2 and RQ4: how aspect sentiment and trust concerns differ by platform",
            "Answer RQ3: which model is most reliable for this task",
            "Test H1-H4 as hypotheses; answer RQ5 on what platforms can improve",
        ],
    )
    set_notes(
        s,
        "Four objectives: an aspect taxonomy, a cross-platform comparison, a "
        "fair model comparison and actionable insights. The hypotheses H1 to "
        "H4 are stated up front and tested - never assumed as findings.",
    )

    # ================= SLIDE 7 - Literature Survey =================
    s = S[6]
    sh = by_name(s)
    rewrite_tf(sh["Survey stat value 1"], ["[XX]"])
    rewrite_tf(sh["Survey stat label 1"], ["studies reviewed"])
    rewrite_tf(sh["Survey stat value 2"], ["Reviews"])
    rewrite_tf(
        sh["Survey stat label 2"],
        ["main focus: product reviews and eWOM"],
    )
    rewrite_tf(sh["Survey stat value 3"], ["0"])
    rewrite_tf(
        sh["Survey stat label 3"],
        ["studies on Indian refurbished marketplaces"],
    )
    lit = next(x for x in s.shapes if x.has_table).table
    lit_rows = [
        ("Online reviews and eWOM", "Review valence and volume affect sales", "[1]"),
        ("Sentiment analysis", "Opinion mining and polarity classification", "[2], [3]"),
        ("Aspect-based sentiment analysis", "SemEval ABSA shared tasks define the task", "[5], [6]"),
        ("Classical ML", "Feature and lexicon based classifiers", "[3], [4]"),
        ("BERT / transformers", "Attention encoders, fine-tuned for classification", "[7], [8]"),
        (
            "Refurbished context",
            "No dedicated ABSA study found for Indian refurbished marketplaces",
            "-",
        ),
    ]
    for ri, row in enumerate(lit_rows, 1):
        for ci, val in enumerate(row):
            set_cell(lit.rows[ri].cells[ci], val)
    rewrite_tf(
        sh["Survey takeaway"],
        [
            "ABSA and transformers are mature for new products; refurbished "
            "electronics in India remain unexamined.",
        ],
    )
    set_notes(
        s,
        "The survey covers eWOM, sentiment analysis, ABSA, classical machine "
        "learning and transformers, using only the eight references listed at "
        "the end. To our knowledge no study targets Indian refurbished "
        "marketplaces at aspect level.",
    )

    # ================= SLIDE 8 - Research Gap =================
    s = S[7]
    sh = by_name(s)
    gap = next(x for x in s.shapes if x.has_table).table
    # Template header said "Reviewed patents / literature" - no patents here.
    for ci, htext in enumerate(("Aspect", "Existing literature", "This project")):
        set_cell(gap.rows[0].cells[ci], htext)
    gap_rows = [
        (
            "Granularity",
            "Whole-review or document-level labels",
            "Aspect level: nine aspects per review",
        ),
        (
            "Domain",
            "New products, general e-commerce",
            "Refurbished electronics (phones, laptops, DSLR)",
        ),
        (
            "Platforms",
            "Usually one marketplace",
            "Five Indian platforms under one taxonomy",
        ),
        (
            "Method",
            "Classical ML or transformers alone",
            "Both compared on the same split and labels",
        ),
        (
            "Evaluation",
            "Mostly accuracy",
            "Macro precision/recall/F1 plus per-class recall",
        ),
    ]
    for ri, row in enumerate(gap_rows, 1):
        for ci, val in enumerate(row):
            set_cell(gap.rows[ri].cells[ci], val)
    rewrite_tf(sh["Gaps head"], ["Gaps identified"])
    rewrite_tf(
        sh["Gaps points"],
        [
            "No aspect-level sentiment study of refurbished electronics in India",
            "No common aspect taxonomy applied across five Indian marketplaces",
            "Classical ML and BERT are rarely compared on the same split for this domain",
            "Neutral and mixed reviews are usually dropped; here they are kept and evaluated",
        ],
    )
    set_notes(
        s,
        "Five gaps: granularity, domain, platforms, method and evaluation. "
        "Each one is addressed directly by this project's design.",
    )

    # ================= SLIDE 9 - Problem Statement =================
    s = S[8]
    sh = by_name(s)
    rewrite_tf(
        sh["Problem statement text"],
        [
            "Refurbished electronics reviews are mixed, platform-specific and hard "
            "to summarise with a single label; an aspect-level, multi-model "
            "analysis is needed to show what drives trust and dissatisfaction.",
        ],
    )
    needs = [
        (
            "Mixed opinions",
            "The same review can praise the battery and blame delivery; one label "
            "cannot capture this.",
        ),
        (
            "Platforms differ",
            "Cashify, OLX and Budli differ in fulfilment and trust, so sentiment "
            "patterns may differ by aspect.",
        ),
        (
            "Class imbalance",
            "Neutral and negative mentions are fewer; macro metrics are needed to "
            "avoid biased evaluation.",
        ),
    ]
    for i, (head, text) in enumerate(needs, 1):
        rewrite_tf(sh[f"Need head {i}"], [head])
        rewrite_tf(sh[f"Need text {i}"], [text])
    rewrite_tf(
        sh["Scope text"],
        [
            "Scope: India; five platforms; three product categories; nine aspects; "
            "three polarity labels. Demo corpus is synthetic until verified "
            "platform reviews are obtained.",
        ],
    )
    set_notes(
        s,
        "The core problem: mixed reviews, different platform models and class "
        "imbalance. Scope is India, five platforms, three categories, nine "
        "aspects and three labels.",
    )

    # ================= SLIDE 10 - Proposed Methodology =================
    s = S[9]
    sh = by_name(s)
    steps = [
        ("1. Review collection", "Access verified per platform; 2,000-review demo corpus, seed 42"),
        ("2. Cleaning", "Lowercasing, punctuation, de-duplication, length filter"),
        ("3. Aspect tagging", "Keyword vocabulary over nine aspects; one annotation per mention"),
        ("4. Sentiment labelling", "Positive / Neutral / Negative; 10% label noise for realism"),
        ("5. Model training", "TF-IDF + LR / RF / XGBoost and DistilBERT; 70/15/15 split"),
        ("6. Platform comparison", "Aspect sentiment shares and net sentiment per platform"),
    ]
    for i, (head, text) in enumerate(steps, 1):
        rewrite_tf(sh[f"Step {i}"], [head])
        rewrite_tf(sh[f"Step text {i}"], [text])
    rewrite_tf(
        sh["Stages label"],
        [
            "Stages: Verify > Dataset > Annotate > Model > Evaluate > Compare platforms",
        ],
    )
    set_notes(
        s,
        "Six stages from review collection to platform comparison. The split "
        "is fixed at seed 42, so every model is trained and tested on "
        "exactly the same partitions.",
    )

    # ================= SLIDE 11 - Methodology: Dataset =================
    s = S[10]
    sh = by_name(s)
    rewrite_tf(sh["Dataset stat value 1"], ["2,000"])
    rewrite_tf(sh["Dataset stat label 1"], ["total reviews (demo)"])
    rewrite_tf(sh["Dataset stat value 2"], ["3,548"])
    rewrite_tf(sh["Dataset stat label 2"], ["aspect annotations"])
    rewrite_tf(sh["Dataset stat value 3"], ["5"])
    rewrite_tf(sh["Dataset stat label 3"], ["platforms, 3 categories"])
    set_chart(
        sh["Class distribution chart"],
        ["Cashify", "Amazon Renewed", "Flipkart Ref.", "OLX", "Budli"],
        "Reviews",
        (492, 485, 379, 361, 283),
        title="Reviews per platform",
    )
    rewrite_tf(
        sh["Dataset details"],
        [
            "Source: synthetic demo corpus (generate_dataset.py v2, seed 42), built after verifying platform review access; real collection pending",
            "Categories: Smartphone 989, Laptop 595, DSLR / Camera 416",
            "Fields: review text, marketplace, category, aspect, evidence phrase, sentiment",
            "Labels: Positive 1,691 (47.7%), Negative 1,120 (31.6%), Neutral 737 (20.8%)",
            "Split: train 2,475 / validation 536 / test 537 (review-level, seed 42)",
        ],
    )
    set_notes(
        s,
        "The demo corpus has 2,000 reviews and 3,548 aspect annotations, "
        "generated after verifying that the five platforms do not expose "
        "scrapeable reviews. Every data value in this deck is computed from "
        "this labelled corpus - nothing is invented.",
    )

    # ================= SLIDE 12 - Methodology: Pre-processing ==========
    s = S[11]
    sh = by_name(s)
    rewrite_tf(sh["Technique head 1"], ["Cleaning"])
    rewrite_tf(
        sh["Technique points 1"],
        [
            "Lowercasing and punctuation normalisation",
            "Remove duplicates and near-empty reviews",
            "Keep negation ('not good') and contrast ('but') markers",
            "Filter very short, uninformative texts",
        ],
    )
    rewrite_tf(sh["Technique head 2"], ["Aspect tagging"])
    rewrite_tf(
        sh["Technique points 2"],
        [
            "Product condition, Battery health, Performance",
            "Price and value, Packaging and delivery",
            "Repair and refurbishment quality",
            "Seller and customer service",
            "Returns and refunds, Trust and authenticity",
            "One annotation per mention, evidence phrase stored",
        ],
    )
    rewrite_tf(sh["Technique head 3"], ["Labels and split"])
    rewrite_tf(
        sh["Technique points 3"],
        [
            "Three labels: Positive / Neutral / Negative",
            "Review-level stratified 70/15/15, seed 42",
            "Same held-out test set used for every model",
            "10% label noise simulates annotator disagreement",
        ],
    )
    rewrite_tf(
        sh["Test preprocessing text"],
        [
            "Negation and contrast words are kept through cleaning, since "
            "'good battery but cracked screen' must survive to the aspect stage.",
        ],
    )
    set_notes(
        s,
        "Cleaning keeps negation and contrast markers because they decide "
        "aspect polarity. Aspect tagging produces one annotation per mention "
        "with its evidence phrase, and the split is review-level to prevent "
        "leakage between partitions.",
    )

    # ================= SLIDE 13 - Methodology: Models ==================
    s = S[12]
    sh = by_name(s)
    rewrite_tf(sh["CNN card head"], ["TF-IDF classical models"])
    rewrite_tf(
        sh["CNN points"],
        [
            "TF-IDF n-gram features over annotation text",
            "Logistic Regression with balanced class weights",
            "Random Forest and XGBoost on the same features",
            "Fast, interpretable baselines",
        ],
    )
    rewrite_tf(sh["TL card head"], ["BERT fine-tuning"])
    rewrite_tf(
        sh["TL points"],
        [
            "distilbert-base-uncased with a 3-class head",
            "Trained on the training partition only",
            "Best epoch on validation; tested once",
            "CPU, batch 16, max length 128, lr 2e-5, seed 42",
        ],
    )
    mt = next(x for x in s.shapes if x.has_table).table
    headers = ["Model", "Key idea", "Features", "Notes"]
    for ci, htext in enumerate(headers):
        set_cell(mt.rows[0].cells[ci], htext)
    model_rows = [
        ("Logistic Regression", "Linear margin classifier", "TF-IDF n-grams", "Balanced class weights"),
        ("Random Forest", "Bagged decision trees", "TF-IDF n-grams", "Robust to feature noise"),
        ("XGBoost", "Gradient-boosted trees", "TF-IDF n-grams", "Regularised boosting"),
        (
            "BERT (fine-tuned DistilBERT)",
            "Contextual transformer encoder",
            "Subword embeddings",
            "1 epoch on CPU; best-epoch selection on validation",
        ),
    ]
    for ri, row in enumerate(model_rows, 1):
        for ci, val in enumerate(row):
            set_cell(mt.rows[ri].cells[ci], val)
    set_notes(
        s,
        "Three classical models use TF-IDF features; DistilBERT is "
        "fine-tuned with a three-class head. All models train on the "
        "training partition only and are evaluated once on the same "
        "held-out test set.",
    )

    # ================= SLIDE 14 - Result and Discussion =================
    s = S[13]
    sh = by_name(s)
    set_chart(
        sh["Accuracy chart"],
        ["Log. Reg.", "Random Forest", "XGBoost", "BERT (DistilBERT)"],
        "Accuracy (%)",
        (90.69, 87.15, 86.96, 89.57),
    )
    rewrite_tf(sh["Observations head"], ["Observations"])
    rewrite_tf(
        sh["Observations points"],
        [
            "Logistic Regression highest: 90.69% accuracy, 0.8937 F1",
            "Fine-tuned BERT second: 89.57% accuracy, 0.8784 F1",
            "Random Forest and XGBoost close: about 87%, 0.85 F1",
            "Neutral recall lowest for every model (0.70-0.75)",
            "BERT did not beat the best classical model here",
        ],
    )
    rewrite_tf(sh["Iterations head"], ["Training and evaluation"])
    rewrite_tf(
        sh["Iterations points"],
        [
            "All models: same review-level stratified split (seed 42), evaluated once on the same held-out test set | "
            "Macro precision / recall / F1 reported to handle class imbalance | CPU-only training",
        ],
    )
    set_notes(
        s,
        "Logistic Regression is highest on this demo data at 90.69% accuracy "
        "and fine-tuned BERT is second at 89.57%. Neutral recall is the "
        "weakest point for every model, which matches the injected "
        "ambiguity. Results characterize the pipeline on synthetic data.",
    )

    # ================= SLIDE 15 - Result: Aspect & Platform ============
    s = S[14]
    sh = by_name(s)
    # Replace the prediction-grid picture with a heatmap placeholder card.
    pic = sh["Prediction grid"]
    pic._element.getparent().remove(pic._element)
    ph = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.40), Inches(1.30), Inches(4.50), Inches(2.30)
    )
    ph.fill.solid()
    ph.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    ph.line.color.rgb = NAVY
    ph.line.width = Pt(1.25)
    tf = ph.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = (
        "Aspect x platform net-sentiment heatmap - placeholder "
        "(to be rendered from Table 6 outputs)"
    )
    r.font.name = "Times New Roman"
    r.font.size = Pt(13)
    r.font.italic = True
    r.font.color.rgb = GREY
    rewrite_tf(
        sh["Grid caption"],
        ["Aspect x platform sentiment (placeholder)"],
    )
    rewrite_tf(
        sh["Prediction points"],
        [
            "Returns and refunds: highest negative share on most platforms",
            "OLX lowest on seller service (-8.1) and trust (-4.3) in demo data",
            "Cashify leads seller and customer service (+46.6)",
            "Demo-data patterns; re-check on verified real reviews",
        ],
    )
    met = next(x for x in s.shapes if x.has_table).table
    metric_rows = [
        ("Accuracy", "Overall share of correct predictions on the test set"),
        ("Precision", "When a label is predicted, how often it is right (fewer false alarms)"),
        ("Recall", "How many examples of each class are found; critical for negative complaints"),
        ("Macro F1", "Harmonic mean of precision and recall, averaged over the three classes"),
        ("Confusion matrix", "Shows which classes are confused - here neutral is most often missed"),
    ]
    set_cell(met.rows[0].cells[0], "Metric")
    set_cell(met.rows[0].cells[1], "What it tells us")
    for ri, row in enumerate(metric_rows, 1):
        set_cell(met.rows[ri].cells[0], row[0])
        set_cell(met.rows[ri].cells[1], row[1])
    set_notes(
        s,
        "Returns and refunds and trust show the highest negative shares in "
        "the demo data, and OLX is weakest on seller service. These patterns "
        "will be re-checked once real platform reviews are collected. The "
        "metric table explains how results are read.",
    )

    # ================= SLIDE 16 - Outcome ==============================
    s = S[15]
    sh = by_name(s)
    rewrite_tf(sh["IP card head"], ["Research output"])
    rewrite_tf(
        sh["IP points"],
        [
            "RefurbIQ paper draft in progress: all six results tables filled from computed outputs",
            "Planned venue: [XX]",
            "Every reported number is reproducible via the scripts in research/scripts/",
            "Dataset is labelled synthetic; real-review validation is the next step",
        ],
    )
    rewrite_tf(sh["Deliverables card head"], ["Deliverables"])
    rewrite_tf(
        sh["Deliverables points"],
        [
            "Labelled dataset: 2,000 reviews, 3,548 aspect annotations",
            "Reproducible Python code (pushed to GitHub)",
            "Nine-aspect taxonomy for refurbished electronics",
            "Four-model comparison on a common leak-free protocol",
        ],
    )
    rewrite_tf(
        sh["Draft title text"],
        [
            "Paper title: RefurbIQ: Aspect-Based Sentiment Analysis of Refurbished "
            "Electronics Across Indian Marketplaces - draft in progress.",
        ],
    )
    set_notes(
        s,
        "The outcome is a paper draft in progress plus four deliverables: "
        "the labelled dataset, reproducible code, the aspect taxonomy and "
        "the model comparison. The planned venue is not finalised yet.",
    )

    # ================= SLIDE 17 - References ===========================
    s = S[16]
    sh = by_name(s)
    refs = [
        (
            "[1]",
            "A. Chevalier and M. Mayzlin, \u201cThe effect of word of mouth on sales: "
            "Online book reviews,\u201d J. Marketing Research, vol. 43, no. 3, pp. 345\u2013354, 2006.",
        ),
        (
            "[2]",
            "B. Liu, Sentiment Analysis and Opinion Mining. Morgan & Claypool, 2012.",
        ),
        (
            "[3]",
            "B. Pang and L. Lee, \u201cOpinion mining and sentiment analysis,\u201d Foundations "
            "and Trends in Information Retrieval, vol. 2, no. 1\u20132, pp. 1\u2013135, 2008.",
        ),
        (
            "[4]",
            "M. Hu and B. Liu, \u201cMining and summarizing customer reviews,\u201d in Proc. KDD, "
            "2004, pp. 168\u2013177.",
        ),
        (
            "[5]",
            "M. Pontiki et al., \u201cSemEval-2014 Task 4: Aspect based sentiment analysis,\u201d "
            "in Proc. SemEval, 2014, pp. 27\u201335.",
        ),
        (
            "[6]",
            "M. Pontiki et al., \u201cSemEval-2016 Task 5: Aspect based sentiment analysis,\u201d "
            "in Proc. SemEval, 2016, pp. 19\u201330.",
        ),
        (
            "[7]",
            "A. Vaswani et al., \u201cAttention is all you need,\u201d in Proc. NeurIPS, 2017, "
            "pp. 5998\u20136008.",
        ),
        (
            "[8]",
            "J. Devlin et al., \u201cBERT: Pre-training of deep bidirectional transformers,\u201d "
            "in Proc. NAACL-HLT, 2019, pp. 4171\u20134186.",
        ),
    ]
    for i, (rid, rtext) in enumerate(refs, 1):
        rewrite_tf(sh[f"Reference id {i}"], [rid])
        rewrite_tf(sh[f"Reference text {i}"], [rtext])
    rewrite_tf(
        sh["Reference note"],
        [
            "These eight references are the only sources cited in this presentation.",
        ],
    )
    set_notes(
        s,
        "These eight references are the only sources cited. They cover eWOM, "
        "sentiment analysis, ABSA shared tasks, classical mining methods and "
        "transformers.",
    )

    # Fix slide titles where the template title differs from ours.
    titles = {
        13: "Result and Discussion",          # unchanged
        14: "Result: Aspect and Platform Analysis",
        15: "Outcome: Research Paper and Deliverables",
    }
    for slide_no, new_title in titles.items():
        s = S[slide_no]
        for shape in s.shapes:
            if shape.name == "Title 1" and shape.has_text_frame:
                rewrite_tf(shape, [new_title])
                break

    prs.save(str(OUT))
    print(f"saved base deck: {OUT}")

    # ---------------- SmartArt post-processing (slide 2 outline) --------
    replacements = {
        "Introduction of ": "Introduction",
        "Result and Discussion on Outcome (Conference Paper/ Patent/ Copyrights)":
            "Result and Discussion on Outcome (Research Paper and Deliverables)",
    }
    tmp = OUT.with_suffix(".tmp.pptx")
    with zipfile.ZipFile(OUT) as zin, zipfile.ZipFile(
        tmp, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename in (
                "ppt/diagrams/data2.xml",
                "ppt/diagrams/drawing2.xml",
            ):
                text = data.decode("utf-8")
                for old, new in replacements.items():
                    n = text.count(old)
                    text = text.replace(old, new)
                    print(f"  {item.filename}: replaced {n}x '{old[:40]}...'")
                data = text.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, OUT)
    print("SmartArt outline updated")


if __name__ == "__main__":
    main()