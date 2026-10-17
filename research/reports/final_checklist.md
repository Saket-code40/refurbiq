# RefurbIQ — Final Checklist

## Deliverables

| # | Deliverable | Location | Status |
|---|---|---|---|
| 1 | Review dataset | `research/data/reviews.csv` (2,000 rows, `data_origin=synthetic-demo-v1`) | ✅ |
| 2 | Aspect annotations | `research/data/aspect_annotations.csv` (3,548 rows) | ✅ |
| 3 | Model predictions (test partition, all models) | `research/data/model_predictions.csv` | ✅ (fine-tuned column added when training finishes) |
| 4 | Table 1 — dataset profile | `research/tables/table1_dataset_profile.csv` | ✅ |
| 5 | Table 2 — aspect frequency | `research/tables/table2_aspect_frequency.csv` | ✅ |
| 6 | Table 3 — model performance | `research/tables/table3_model_performance.csv` | ✅ (fine-tuned row pending) |
| 7 | Table 4 — class-specific recall | `research/tables/table4_class_specific_recall.csv` | ✅ (fine-tuned row pending) |
| 8 | Table 5 — sentiment by aspect | `research/tables/table5_sentiment_by_aspect.csv` | ✅ |
| 9 | Table 6 — cross-platform | `research/tables/table6_cross_platform.csv` | ✅ |
| 10 | Reproducible scripts | `research/scripts/*.py` (8 scripts, seeds fixed) | ✅ |
| 11 | Validation report | `research/reports/validation_report.md` | ✅ |
| 12 | Methodology report | `research/reports/methodology_report.md` | ✅ |
| 13 | Final checklist | this file | ✅ |
| 14 | Edited paper | `research/reports/RefurbIQ_completed.docx` | ✅ 0 `[Insert]` placeholders remain (BERT row switches to fine-tuned numbers when available) |

## Research-integrity rules — compliance check

| Rule | Compliant? | Evidence |
|---|---|---|
| Never fabricate review data / dataset sizes / metrics / citations | ✅ | all data synthetic and labeled; all metrics computed by scripts |
| Never claim training/evaluation that did not happen | ✅ | fine-tuned row only added after the run completes |
| Never infer reviewer location from seller/origin | ✅ | no reviewer-location field exists or is claimed |
| Distinguish verified / external / assumed / limited | ✅ | methodology_report.md §1, §9 |
| Do not report expected outcomes as findings | ✅ | platform deltas are documented assumptions, not findings |
| Every number reproducible from data/evaluation | ✅ | build_tables.py computes all six CSVs; no hand-entered values |
| Insufficient evidence → say what is missing | ✅ | platform verification documented; synthetic strategy user-approved with caveats |
| Respect site terms; no CAPTCHA/auth/rate-limit bypass | ✅ | access checks were passive HTTP GETs only |
| Synthetic examples never presented as real | ✅ | `data_origin` column + provenance note in docx |

## Known pending items

- [x] DistilBERT fine-tuning run completes → `bert_finetuned_metrics.json`
      (1 epoch, CPU; acc 0.8957, macro F1 0.8784)
- [x] Re-run `build_tables.py` (adds fine-tuned rows to tables 3/4)
- [x] Re-run `update_docx.py` (docx BERT row carries fine-tuned numbers;
      zero-shot documented as separate configuration)
- [x] Update methodology report §7 with fine-tuned numbers
- [ ] Commit research artifacts (push to GitHub only after user confirms)

Deliverable status: all six `[Insert]` tables filled (0 remaining),
all numbers computed by `research/scripts/build_tables.py` from
`research/data/` — no hand-entered values. Data is synthetic
(`data_origin = synthetic-demo-v1`) and labeled as such everywhere.