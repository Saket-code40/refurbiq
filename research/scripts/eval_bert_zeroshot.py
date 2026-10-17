"""BERT-based evaluation, stage 1: zero-shot with a pre-trained sentiment model.

Evaluates a public sentiment model on the SAME held-out test partition as
the traditional models (split_assignment.csv), so Tables 3-4 compare all
models on identical examples (paper §7.10).

Configuration reported per paper §7.8:
    - Checkpoint: cardiffnlp/twitter-roberta-base-sentiment-latest
      (RoBERTa-base sentiment head: negative/neutral/positive).
      NOTE: this is a zero-shot application of an out-of-domain pre-trained
      model, NOT fine-tuning. The fine-tuned variant is produced separately
      by finetune_bert.py and its row added later.
    - Input: the annotated evidence phrase only (unit of analysis matches
      the traditional models).
    - Batch size 16, max length 128, CPU inference, seed 42.

Output: bert_zeroshot_metrics.json (+ predictions appended to
        model_predictions.csv as pred_bert_zeroshot).

Usage:
    python eval_bert_zeroshot.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import torch
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

SEED = 42
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LABELS = ["positive", "neutral", "negative"]
MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"
BATCH_SIZE = 16
MAX_LENGTH = 128


def evaluate(y_true, y_pred) -> dict:
    acc = accuracy_score(y_true, y_pred)
    _, r, _, support = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, average=None, zero_division=0
    )
    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, average="macro", zero_division=0
    )
    return {
        "accuracy": round(float(acc), 4),
        "macro_precision": round(float(macro_p), 4),
        "macro_recall": round(float(macro_r), 4),
        "macro_f1": round(float(macro_f1), 4),
        "class_recall": {lab: round(float(x), 4) for lab, x in zip(LABELS, r)},
        "class_support": {lab: int(s) for lab, s in zip(LABELS, support)},
    }


def main() -> None:
    torch.manual_seed(SEED)

    annotations = pd.read_csv(DATA_DIR / "aspect_annotations.csv")
    split = pd.read_csv(DATA_DIR / "split_assignment.csv")
    test_ids = split.loc[split.partition == "test", "annotation_id"]
    test = annotations[annotations.annotation_id.isin(test_ids)].reset_index(drop=True)
    print(f"test annotations: {len(test)}")

    from transformers import pipeline

    device = 0 if torch.cuda.is_available() else -1
    classifier = pipeline(
        "sentiment-analysis",
        model=MODEL_NAME,
        tokenizer=MODEL_NAME,
        device=device,
        truncation=True,
        max_length=MAX_LENGTH,
    )

    # The HF model outputs labels 'negative'/'neutral'/'positive' directly.
    preds: list[str] = []
    for start in range(0, len(test), BATCH_SIZE):
        batch = test["evidence_phrase"].iloc[start : start + BATCH_SIZE].tolist()
        for out in classifier(batch):
            label = out["label"].lower().strip()
            preds.append(label if label in LABELS else "neutral")

    metrics = evaluate(test["sentiment"], preds)
    metrics.update(
        {
            "configuration": "zero-shot (no fine-tuning)",
            "checkpoint": MODEL_NAME,
            "batch_size": BATCH_SIZE,
            "max_length": MAX_LENGTH,
            "device": "cuda" if device == 0 else "cpu",
            "seed": SEED,
            "n_test": len(test),
            "provenance": "SYNTHETIC demonstration dataset (generate_dataset.py v2)",
        }
    )
    with (DATA_DIR / "bert_zeroshot_metrics.json").open("w") as f:
        json.dump(metrics, f, indent=2)

    # Append predictions to the shared predictions file.
    pred_path = DATA_DIR / "model_predictions.csv"
    preds_df = pd.read_csv(pred_path)
    preds_df["pred_bert_zeroshot"] = pd.Series(preds).values
    preds_df.to_csv(pred_path, index=False)

    print(
        f"BERT zero-shot: acc={metrics['accuracy']:.4f} "
        f"macroF1={metrics['macro_f1']:.4f} class-recall={metrics['class_recall']}"
    )


if __name__ == "__main__":
    main()