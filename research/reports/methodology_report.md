# RefurbIQ — Methodology Report

**Status:** all reported numbers are computed by the scripts in `research/scripts/`
from the data in `research/data/`. Nothing in this report is hand-entered.
**Data origin:** every review and annotation carries
`data_origin = "synthetic-demo-v1"`. The dataset is **synthetic** (see §2–§3);
it demonstrates and validates the full pipeline end-to-end. It is **not** a
sample of real marketplace reviews.

---

## 1. Platform verification (done before any data work)

Before deciding on a data strategy, each target marketplace was checked for
publicly accessible, structured product reviews:

| Platform | Verified access outcome |
|---|---|
| Cashify | Public testimonials exist; no structured per-product review API reachable |
| Amazon Renewed (IN) | Renewed storefront not reachable (HTTP 404) |
| Flipkart Refurbished | Site reachable; no scrape-permitted structured review endpoint identified |
| OLX | HTTP 403 / timeouts; peer-to-peer listings without structured reviews |
| Budli | Public testimonials exist; no structured review feed |
| HuggingFace datasets | No refurbished-electronics or Indian-marketplace ABSA dataset found |

Access checks respected each site's terms and rate limits; no CAPTCHAs,
authentication walls, or rate limits were bypassed.

**Consequence (user-approved):** tables are filled from a clearly-labeled
synthetic demo dataset with explicit caveats, rather than leaving them empty.
No real review text, dataset size, or marketplace statistic is claimed.

## 2. Synthetic dataset generation

Script: `research/scripts/generate_dataset.py` (v2), seed **42**.

- 2,000 reviews → 3,548 aspect–sentiment annotations.
- Platforms: Cashify, Amazon Renewed, Flipkart Refurbished, OLX, Budli.
- Categories: Smartphone, Laptop, Camera.
- Base sentiment mix: positive 0.52 / neutral 0.16 / negative 0.32.
- Per-platform sentiment deltas (`PLATFORM_BIAS`) are documented in the
  script header; they are modeling assumptions, not observed marketplace facts.
- **Label noise:** `LABEL_NOISE_RATE = 0.10` — 10% of labels are flipped to an
  adjacent class (pos↔neu, neu↔neg) to simulate annotator disagreement.
- **Lexical ambiguity:** `AMBIGUOUS_SHARE = 0.30` of texts are drawn from
  cross-class ambiguous templates, so classes are not trivially separable
  (the first generator version produced 100%-accuracy baselines; noise and
  ambiguity were added specifically to make the task realistic).
- Every row records `annotator_id = "generate_dataset.py v2"` and
  `data_origin = "synthetic-demo-v1"`; 325 annotations carry a
  disagreement flag.

## 3. Annotation scheme

- Aspect detection: deterministic keyword matching over 9 aspects
  (Product condition, Battery health, Performance, Price and value,
  Packaging and delivery, Repair and refurbishment quality,
  Seller and customer service, Returns and refunds, Trust and authenticity).
- Sentiment labels: positive / neutral / negative per aspect mention.
- Because one generator pass produces both text and labels, there is exactly
  one annotator per example. Inter-annotator agreement statistics are
  therefore **not** reported — reporting them would require fabricating a
  second annotator.

## 4. Experimental protocol

Script: `research/scripts/train_traditional_models.py` (split section).

- **Split:** review-level stratified 70/15/15 (train/val/test), seed 42.
  Stratification is at review level so all annotations of one review stay in
  one partition (no leakage through shared text).
  Result: train 2,475 / val 536 / test 537 annotations
  (test: 250 positive / 172 negative / 115 neutral).
  Saved: `research/data/split_assignment.csv`.
- **All models are evaluated on the identical held-out test set.**
- Predictions for every model on the test set:
  `research/data/model_predictions.csv` (one column per model).

## 5. Models

| Model | Configuration |
|---|---|
| Logistic Regression | TF-IDF features, balanced class weights |
| Random Forest | TF-IDF features, balanced class weights |
| XGBoost | TF-IDF features, integer label codes, sample-weight balancing |
| BERT zero-shot | `cardiffnlp/twitter-roberta-base-sentiment-latest`, no training, evaluated on test partition (`eval_bert_zeroshot.py`) |
| BERT fine-tuned | `distilbert-base-uncased`, 3 epochs, batch 16, max length 128, lr 2e-5, weight decay 0.01, seed 42, CPU (`finetune_bert.py`) |

Notes:
- The fine-tuned model's classification head (`pre_classifier`, `classifier`)
  is randomly initialized at load, as expected for a new downstream task.
- Fine-tuning ran without GPU; this is a resource constraint, not a
  methodological choice.

## 6. Metrics

Computed with scikit-learn on the test partition only:
accuracy, macro precision, macro recall, macro F1, and per-class recall
(positive / negative / neutral). Macro averaging is used because the test
classes are imbalanced.

## 7. Reported results (synthetic data)

Table 3 — overall performance (test partition):

| Model | Accuracy | Macro P | Macro R | Macro F1 |
|---|---|---|---|---|
| Logistic Regression | 0.9069 | 0.9167 | 0.8801 | 0.8937 |
| Random Forest | 0.8715 | 0.8620 | 0.8496 | 0.8549 |
| XGBoost | 0.8696 | 0.8577 | 0.8476 | 0.8520 |
| BERT zero-shot | 0.7058 | 0.6705 | 0.6518 | 0.6578 |
| BERT fine-tuned (DistilBERT, 1 epoch) | 0.8957 | 0.9092 | 0.8627 | 0.8784 |

Table 4 — class recall: LR .968/.924/.748, RF .920/.890/.739,
XGB .920/.884/.739, BERT zero-shot .852/.686/.417,
BERT fine-tuned .968/.924/.696 (pos/neg/neu).
Neutral recall is lowest everywhere, consistent with the injected ambiguity.

Note on the BERT row in the paper: the docx's single "BERT-based model"
row carries the **fine-tuned** DistilBERT configuration (distilbert-base-
uncased, 1 epoch, batch 16, max length 128, lr 2e-5, weight decay 0.01,
seed 42, CPU, best-epoch selected on validation). Zero-shot results
(cardiffnlp/twitter-roberta-base-sentiment-latest) are reported separately
in `research/tables/table3_model_performance.csv`. Fine-tuning was limited
to 1 epoch for time; the 3-epoch configuration was not completed.

Interpretation caveat: these numbers characterize **the pipeline on
synthetic data** — they show the evaluation protocol works and is leak-free.
They say nothing about real Indian marketplace reviews.

## 8. Reproducibility

```
research/scripts/generate_dataset.py       # data (seed 42)
research/scripts/train_traditional_models.py  # split + LR/RF/XGB
research/scripts/eval_bert_zeroshot.py     # zero-shot RoBERTa
research/scripts/finetune_bert.py          # fine-tuned DistilBERT
research/scripts/build_tables.py           # six tables → research/tables/
research/scripts/validation_report.py      # research/reports/validation_report.md
research/scripts/update_docx.py            # research/reports/RefurbIQ_completed.docx
```

Every table value in `research/tables/*.csv` and in the completed docx is
derived from these outputs; no value is hand-entered.

## 9. Integrity statement

- Verified observations: platform access outcomes (§1), all computed metrics.
- Synthetic/assumed: all review content, dataset sizes, sentiment mixes,
  platform bias deltas.
- Not reported (would require fabrication): inter-annotator agreement,
  real marketplace statistics, price/availability data.
- The completed paper (`RefurbIQ_completed.docx`) contains a provenance note
  stating that Tables 1–6 are filled from the synthetic demo dataset.

## 10. Limitations

1. Fully synthetic corpus — findings do not transfer to real reviews.
2. Single annotator per example; no agreement statistics.
3. Keyword-based aspect detection (honest labeling: clause-level sentiment
   pipeline, not a jointly-trained ABSA model).
4. CPU-only fine-tuning limits model size and hyperparameter search.
5. Five platforms modeled; real availability/warranty policies differ.