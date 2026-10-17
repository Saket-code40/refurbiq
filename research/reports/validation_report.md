# RefurbIQ Paper — Validation and Data-Quality Report

Generated: 2026-10-16

**Provenance:** all findings below derive from the SYNTHETIC demonstration dataset produced by `generate_dataset.py v2` (seed 42). No value in this report is based on authentic marketplace reviews.

## 1. Row counts
- reviews.csv: 2000 rows x 10 columns
- aspect_annotations.csv: 3548 rows x 7 columns
- split_assignment.csv: 3548 rows (one per annotation)
- model_predictions.csv: 537 rows
- Annotations per review: 1.77 on average
- model_predictions.csv covers the test partition only (537 annotations); no prediction rows exist outside it.

## 2. Duplicate checks (documented dedup rule: exact-text)
- Exact duplicate review texts: 0
- Duplicate review_ids: 0
- Duplicate annotation_ids: 0

## 3. Missing fields
- reviews: {'review_id': 0, 'review_text': 0, 'marketplace': 0, 'product_category': 0, 'product_name': 0, 'rating': 0, 'review_date': 0, 'source_url': 2000, 'collection_date': 0, 'data_origin': 0}
- annotations: {'annotation_id': 0, 'review_id': 0, 'aspect': 0, 'sentiment': 0, 'evidence_phrase': 0, 'annotation_status': 0, 'annotator_id': 0}
- Note: `source_url` is empty by design for the synthetic demo (no real URLs exist); it must be populated from the verified collection log before submission.

## 4. Split integrity
- Unique reviews per partition: {'test': 300, 'train': 1400, 'validation': 300}
- Reviews shared between train and test: 0 (must be 0)
- Annotation counts per partition: {'test': 537, 'train': 2475, 'validation': 536}
- Split was made at review level (stratified on majority sentiment), seed 42.

## 5. Annotation counts
- Total aspect mentions: 3548
- positive: 1691 (47.7%)
- neutral: 737 (20.8%)
- negative: 1120 (31.6%)
- Simulated annotation-disagreement labels: 325 (9.2%)
- Aspects covered: 9 of 9

## 6. Model prediction coverage
- Prediction columns: ['pred_logreg', 'pred_random_forest', 'pred_xgboost', 'pred_bert_zeroshot']
  - pred_logreg: 537 predictions
  - pred_random_forest: 537 predictions
  - pred_xgboost: 537 predictions
  - pred_bert_zeroshot: 537 predictions

## 7. Arithmetic consistency
- Sum of per-platform review counts equals total: True
- Sum of aspect mentions equals annotation rows: True

## 8. Remaining placeholders that cannot yet be filled
- Any claim about REAL customer sentiment (dataset is synthetic).
- `source_url` and real `collection_date` per platform.
- Inter-annotator agreement (Cohen's kappa) — single auto-annotator demo.
- Fine-tuned BERT row in Tables 3-4 — pending completion of finetune_bert.py run.
