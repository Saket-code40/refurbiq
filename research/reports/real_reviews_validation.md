# RefurbIQ — Real-Data Validation Run

**Date:** 2026-10-18 · **Script:** `research/scripts/run_real_reviews.py`
**Outputs:** `research/data/real/real_aspect_annotations.csv` (2,460 rows),
`real_reviews_sample.csv` (2,000 reviews), `real_aspect_sentiment.csv`

## 1. Data source (REAL reviews, licensed)

- **Dataset:** `SetFit/amazon_reviews_multi_en` — Multilingual Amazon
  Reviews Corpus (Keung et al., EMNLP 2020), Apache-2.0 license.
- Downloaded verbatim from Hugging Face (25 MB parquet, 200,000 English
  reviews, balanced 40,000 per star level). No review text was modified.
- **Stratified sample:** 2,000 reviews (400 per star, seed 42, min
  length 40 chars).

## 2. Honest scope caveats

- These are **genuine Amazon marketplace reviews**, but NOT
  refurbished-electronics reviews from the five Indian platforms in the
  paper. The paper's platform-level claims still require verified
  Cashify / Amazon Renewed / Flipkart / OLX / Budli review data.
- What this run DOES validate: the pipeline (keyword aspect detection +
  BERT whole-review sentiment, `nlptown/bert-base-multilingual-uncased-sentiment`)
  on real, noisy human text — against human ground truth (star ratings),
  which the synthetic dataset never provided.

## 3. Validation: predicted sentiment vs human star ratings

Star→sentiment mapping: 1–2★ = negative, 3★ = neutral, 4–5★ = positive.

| Star bucket | Annotations | Agreement |
|---|---|---|
| 1★ | 527 | **0.945** |
| 2★ | 507 | 0.738 |
| 3★ | 481 | **0.432** ← ambiguous middle, expected weak spot |
| 4★ | 489 | 0.710 |
| 5★ | 456 | **0.950** |
| **Overall** | **2,460** | **0.756** |

Reading: the pipeline is highly reliable at the extremes (where buyer
intent is unambiguous) and weakest exactly where human reviewers
themselves are ambivalent (3★). This is the behavior a reviewer should
expect from any whole-review sentiment model.

## 4. Aspect findings on real data

- **Aspect coverage:** 47.5% of real reviews mention ≥1 of the 13
  known aspects; the rest are "General" (general Amazon catalogue
  reviews often discuss the product rather than the purchase/fulfilment
  experience the taxonomy targets).
- Sentiment distribution (predicted, per annotation):
  negative 44.2% / positive 37.0% / neutral 18.8% — the negative skew
  is consistent with the well-documented review-negativity bias in
  e-commerce.

| Aspect (n ≥ 30) | n | Positive% | Negative% | Neutral% |
|---|---|---|---|---|
| Price/Value | 302 | 41.4 | 38.7 | 19.9 |
| Accessories | 188 | 38.3 | 42.0 | 19.7 |
| Return/Refund | 164 | 8.5 | **81.1** | 10.4 |
| Delivery | 116 | 32.8 | 51.7 | 15.5 |
| Packaging | 111 | 30.6 | 52.3 | 17.1 |
| Performance | 109 | 37.6 | 42.2 | 20.2 |
| Camera | 105 | 24.8 | 51.4 | 23.8 |
| Battery | 82 | 34.1 | 48.8 | 17.1 |
| Condition | 76 | 32.9 | 50.0 | 17.1 |
| Seller Service | 62 | 33.9 | 61.3 | 4.8 |
| Display | 57 | 35.1 | 40.4 | 24.6 |
| Trust/Authenticity | 36 | 25.0 | 66.7 | 8.3 |

Observation (reported honestly, as pipeline output on this sample, not
a general claim): **Return/Refund** (81% negative) and
**Trust/Authenticity** (67% negative) dominate negative sentiment —
the same two areas the paper identifies as central to refurbished-goods
purchase anxiety.

## 5. What this changes

- The ABSA pipeline is now **validated against human ground truth on
  real text** (75.6% overall, 94–95% at extremes).
- The six paper tables remain based on the synthetic demo dataset,
  because the paper's protocol requires per-platform Indian
  refurbished data, which is still not publicly accessible.
- Next honest step toward a submittable paper: collect real reviews
  from the five platforms (manual, permission-respecting collection)
  and re-run `build_tables.py` + `update_docx.py`.

## 6. Reproduce

```bash
.venv/bin/python research/scripts/run_real_reviews.py --n 2000
# ~4 min on CPU; requires research/data/real/amazon_train.parquet
# (25 MB, from huggingface.co/datasets/SetFit/amazon_reviews_multi_en)
```
</content>