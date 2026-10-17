"""BERT-based evaluation, stage 2: fine-tuning on the training split (paper §7.8).

Fine-tunes distilbert-base-uncased with a 3-class sentiment head on the
SAME training partition used by the traditional models, then evaluates on
the SAME held-out test partition, so Tables 3-4 remain comparable.

Reported configuration (paper §7.8 reproducibility checklist):
    - Checkpoint: distilbert-base-uncased (CPU-feasible; documented)
    - Input: annotated evidence phrase (same unit of analysis)
    - Split: reuse of split_assignment.csv (no new random partition)
    - Epochs: 3, batch size: 16, max length: 128
    - Learning rate: 2e-5, weight decay: 0.01
    - Random seed: 42 (numpy/torch/dataset)
    - Hardware: CPU (documented in output JSON)

Outputs:
    models/finetuned_distilbert/   saved model + tokenizer
    research/data/bert_finetuned_metrics.json
    pred_bert_finetuned column appended to model_predictions.csv

Usage:
    python finetune_bert.py [--epochs 3]
"""

from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

SEED = 42
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "finetuned_distilbert"
CHECKPOINT = "distilbert-base-uncased"
LABELS = ["positive", "neutral", "negative"]
LABEL2ID = {lab: i for i, lab in enumerate(LABELS)}
BATCH_SIZE = 16
MAX_LENGTH = 128
LR = 2e-5
WEIGHT_DECAY = 0.01


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


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


class TextDataset(Dataset):
    def __init__(self, texts: list[str], labels: list[int], tokenizer) -> None:
        self.enc = tokenizer(
            texts,
            truncation=True,
            max_length=MAX_LENGTH,
            padding="max_length",
            return_tensors="pt",
        )
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx: int):
        return {
            "input_ids": self.enc["input_ids"][idx],
            "attention_mask": self.enc["attention_mask"][idx],
            "labels": self.labels[idx],
        }


def predict(model, loader, device) -> list[str]:
    model.eval()
    preds: list[str] = []
    with torch.no_grad():
        for batch in loader:
            out = model(
                input_ids=batch["input_ids"].to(device),
                attention_mask=batch["attention_mask"].to(device),
            )
            ids = out.logits.argmax(dim=-1).cpu().tolist()
            preds.extend(LABELS[i] for i in ids)
    return preds


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=3)
    args = parser.parse_args()

    set_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    # Keep CPU utilization bounded: the previous run spawned the default
    # OpenMP pool (38 threads on this 8-core box), contended, and stalled
    # at ~4% utilization. A bounded pool trains several times faster here.
    n_threads = min(8, os.cpu_count() or 1)
    torch.set_num_threads(n_threads)
    print(f"device={device} torch_threads={n_threads}", flush=True)

    annotations = pd.read_csv(DATA_DIR / "aspect_annotations.csv")
    split = pd.read_csv(DATA_DIR / "split_assignment.csv")
    df = annotations.merge(split, on="annotation_id")
    train = df[df.partition == "train"].reset_index(drop=True)
    val = df[df.partition == "validation"].reset_index(drop=True)
    test = df[df.partition == "test"].reset_index(drop=True)
    print(f"train={len(train)} val={len(val)} test={len(test)}")

    tokenizer = AutoTokenizer.from_pretrained(CHECKPOINT)
    model = AutoModelForSequenceClassification.from_pretrained(
        CHECKPOINT, num_labels=len(LABELS), id2label=dict(enumerate(LABELS)),
        label2id=LABEL2ID,
    )
    model.to(device)

    train_ds = TextDataset(
        train["evidence_phrase"].tolist(),
        train["sentiment"].map(LABEL2ID).tolist(),
        tokenizer,
    )
    val_ds = TextDataset(
        val["evidence_phrase"].tolist(),
        val["sentiment"].map(LABEL2ID).tolist(),
        tokenizer,
    )
    test_ds = TextDataset(
        test["evidence_phrase"].tolist(),
        test["sentiment"].map(LABEL2ID).tolist(),
        tokenizer,
    )
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE)
    test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE)

    # torch's own AdamW replaces the deprecated transformers.AdamW
    # (removed in transformers >= 5); numerically identical.
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=int(0.1 * total_steps), num_training_steps=total_steps
    )

    # Train, selecting the best checkpoint on the validation partition
    # (hyperparameter/model selection never touches the test partition).
    best_f1, best_epoch, best_state = -1.0, -1, None
    for epoch in range(1, args.epochs + 1):
        model.train()
        for step, batch in enumerate(train_loader, 1):
            out = model(
                input_ids=batch["input_ids"].to(device),
                attention_mask=batch["attention_mask"].to(device),
                labels=batch["labels"].to(device),
            )
            out.loss.backward()
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            if step % 25 == 0:
                print(
                    f"  epoch {epoch} step {step}/{len(train_loader)} "
                    f"loss={out.loss.item():.4f}",
                    flush=True,
                )

        val_pred = predict(model, val_loader, device)
        val_f1 = evaluate(val["sentiment"], val_pred)["macro_f1"]
        print(f"epoch {epoch}: validation macro F1 = {val_f1:.4f}", flush=True)
        if val_f1 > best_f1:
            best_f1, best_epoch = val_f1, epoch
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}

    print(f"best validation epoch: {best_epoch} (macro F1 {best_f1:.4f})")
    model.load_state_dict(best_state)

    test_pred = predict(model, test_loader, device)
    metrics = evaluate(test["sentiment"], test_pred)
    metrics.update(
        {
            "configuration": f"fine-tuned {args.epochs} epochs, best-epoch {best_epoch} on validation",
            "checkpoint": CHECKPOINT,
            "epochs": args.epochs,
            "batch_size": BATCH_SIZE,
            "max_length": MAX_LENGTH,
            "learning_rate": LR,
            "weight_decay": WEIGHT_DECAY,
            "device": str(device),
            "seed": SEED,
            "n_test": len(test),
            "provenance": "SYNTHETIC demonstration dataset (generate_dataset.py v2)",
        }
    )
    with (DATA_DIR / "bert_finetuned_metrics.json").open("w") as f:
        json.dump(metrics, f, indent=2)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(MODEL_DIR)
    tokenizer.save_pretrained(MODEL_DIR)

    pred_path = DATA_DIR / "model_predictions.csv"
    preds_df = pd.read_csv(pred_path)
    preds_df["pred_bert_finetuned"] = pd.Series(test_pred).values
    preds_df.to_csv(pred_path, index=False)

    print(
        f"BERT fine-tuned: acc={metrics['accuracy']:.4f} "
        f"macroF1={metrics['macro_f1']:.4f} class-recall={metrics['class_recall']}"
    )


if __name__ == "__main__":
    main()