"""Train and evaluate the traditional ML baselines (paper §7.7).

Models: Logistic Regression, Random Forest, XGBoost.
Task: 3-class aspect-level sentiment classification on TF-IDF features.

Experimental protocol (paper §7.10):
    - Unit of analysis: one aspect annotation (evidence phrase), matching
      the paper's annotation-level design (§7.6).
    - Split: stratified train/validation/test = 70/15/15, seed=42,
      stratified on the sentiment label.
    - Leakage control: split at review_id level BEFORE aspect expansion so
      no review (or its aspect rows) appears in two partitions.
    - All models share the identical split and feature representation.
    - Class weighting: 'balanced' for LR; class_weight='balanced' for RF;
      sample_weight via balanced class weights for XGBoost.

Outputs (research/data/):
    split_assignment.csv     annotation_id -> partition
    model_predictions.csv    annotation_id, gold, LR/RF/XGB predictions + probs
    traditional_metrics.json per-model accuracy / macro P,R,F1 / per-class recall
    vectorizer params etc. recorded in traditional_metrics.json metadata

Usage:
    python train_traditional_models.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

SEED = 42
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LABELS = ["positive", "neutral", "negative"]


def load_annotations() -> pd.DataFrame:
    annotations = pd.read_csv(DATA_DIR / "aspect_annotations.csv")
    reviews = pd.read_csv(DATA_DIR / "reviews.csv")
    merged = annotations.merge(
        reviews[["review_id", "marketplace", "product_category", "product_name"]],
        on="review_id",
        how="left",
        validate="many_to_one",
    )
    return merged


def split_by_review(df: pd.DataFrame) -> pd.DataFrame:
    """Review-level stratified split to prevent leakage across partitions."""
    review_level = df.groupby("review_id")["sentiment"].agg(
        lambda s: s.mode().iloc[0]
    )
    rids = np.asarray(review_level.index)
    rlabels = np.asarray(review_level)

    train_rids, tmp_rids = train_test_split(
        rids, test_size=0.30, random_state=SEED, stratify=rlabels
    )
    tmp_labels = pd.Series(rlabels, index=rids).loc[tmp_rids].to_numpy()
    val_rids, test_rids = train_test_split(
        tmp_rids, test_size=0.50, random_state=SEED, stratify=tmp_labels
    )

    partition = pd.concat(
        [
            pd.Series("train", index=train_rids),
            pd.Series("validation", index=val_rids),
            pd.Series("test", index=test_rids),
        ]
    )
    df = df.assign(partition=df["review_id"].map(partition))
    return df


def evaluate(y_true, y_pred) -> dict:
    acc = accuracy_score(y_true, y_pred)
    p, r, f1, support = precision_recall_fscore_support(
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
    df = load_annotations()
    df = split_by_review(df)

    # Persist the split so every later script (BERT included) reuses it.
    df[["annotation_id", "review_id", "partition"]].to_csv(
        DATA_DIR / "split_assignment.csv", index=False
    )

    train = df[df.partition == "train"]
    val = df[df.partition == "validation"]
    test = df[df.partition == "test"]
    print(f"sizes: train={len(train)} val={len(val)} test={len(test)}")
    print("test label counts:", test["sentiment"].value_counts().to_dict())

    # TF-IDF on the evidence phrase (the annotated opinion span).
    vectorizer = TfidfVectorizer(
        lowercase=True, ngram_range=(1, 2), max_features=20_000, sublinear_tf=True
    )
    X_train = vectorizer.fit_transform(train["evidence_phrase"])
    X_val = vectorizer.transform(val["evidence_phrase"])
    X_test = vectorizer.transform(test["evidence_phrase"])

    # Hyperparameter tuning is restricted to train/validation (paper §7.10).
    # A small validation-based pick among two LR regularisation strengths.
    results: dict[str, dict] = {}
    predictions = test[["annotation_id", "sentiment"]].rename(
        columns={"sentiment": "gold_label"}
    )

    lr_candidates = [
        LogisticRegression(C=c, class_weight="balanced", max_iter=2000, random_state=SEED)
        for c in (0.5, 1.0, 2.0)
    ]
    best_lr, best_f1 = None, -1.0
    for model in lr_candidates:
        model.fit(X_train, train["sentiment"])
        f1 = precision_recall_fscore_support(
            val["sentiment"], model.predict(X_val), average="macro", zero_division=0
        )[2]
        if f1 > best_f1:
            best_lr, best_f1 = model, f1
    lr_pred = best_lr.predict(X_test)
    results["Logistic Regression"] = evaluate(test["sentiment"], lr_pred)
    results["Logistic Regression"]["chosen_C"] = float(best_lr.C)
    predictions["pred_logreg"] = lr_pred

    rf = RandomForestClassifier(
        n_estimators=400, class_weight="balanced", n_jobs=-1, random_state=SEED
    )
    rf.fit(X_train, train["sentiment"])
    rf_pred = rf.predict(X_test)
    results["Random Forest"] = evaluate(test["sentiment"], rf_pred)
    predictions["pred_random_forest"] = rf_pred

    # Balanced sample weights for XGBoost.
    class_counts = train["sentiment"].value_counts()
    weights = {c: len(train) / (len(LABELS) * n) for c, n in class_counts.items()}
    sample_w = train["sentiment"].map(weights).to_numpy(dtype=float)

    # XGBoost requires integer class codes; map back for evaluation.
    label_to_code = {lab: i for i, lab in enumerate(LABELS)}
    code_to_label = {i: lab for lab, i in label_to_code.items()}
    y_train_code = train["sentiment"].map(label_to_code).to_numpy()
    xgb = XGBClassifier(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.1,
        objective="multi:softmax",
        num_class=len(LABELS),
        eval_metric="mlogloss",
        random_state=SEED,
        n_jobs=-1,
    )
    xgb.fit(X_train, y_train_code, sample_weight=sample_w)
    xgb_pred = [code_to_label[int(c)] for c in xgb.predict(X_test)]
    results["XGBoost"] = evaluate(test["sentiment"], xgb_pred)
    predictions["pred_xgboost"] = xgb_pred

    predictions.to_csv(DATA_DIR / "model_predictions.csv", index=False)

    metadata = {
        "seed": SEED,
        "unit_of_analysis": "aspect annotation (evidence_phrase)",
        "split": "review-level stratified 70/15/15",
        "vectorizer": {
            "type": "TfidfVectorizer",
            "ngram_range": [1, 2],
            "max_features": 20_000,
            "sublinear_tf": True,
        },
        "label_set": LABELS,
        "provenance": "SYNTHETIC demonstration dataset (generate_dataset.py v1)",
        "models": results,
    }
    with (DATA_DIR / "traditional_metrics.json").open("w") as f:
        json.dump(metadata, f, indent=2)

    for name, m in results.items():
        print(
            f"{name:22s} acc={m['accuracy']:.4f} macroF1={m['macro_f1']:.4f} "
            f"class-recall={m['class_recall']}"
        )


if __name__ == "__main__":
    main()