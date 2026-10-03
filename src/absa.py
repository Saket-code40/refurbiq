"""Aspect-Based Sentiment Analysis (ABSA) engine for RefurbIQ.

Architecture note:
  - Aspect identification uses a controlled keyword vocabulary (v0.1).
    This is designed to be replaceable by a fine-tuned aspect extraction
    model in a future version.
  - Sentiment classification uses BERT via Hugging Face Transformers.
    The model classifies: Positive / Neutral / Negative.
  - Sentiment is predicted per aspect-relevant span (clause), NOT on the
    whole review, so mixed reviews produce per-aspect polarities
    (e.g. "looks new but battery drains" -> Condition: Positive,
    Battery: Negative).
  - This is NOT full joint ABSA; it is keyword-based aspect detection
    combined with BERT sentiment on aspect-relevant spans.
"""

import os
import re
from typing import Optional

import pandas as pd

# --- Aspect vocabulary ---
# Each aspect maps to regex patterns used for detection.
# This can later be replaced by a trained aspect extraction model.
ASPECT_KEYWORDS: dict[str, list[str]] = {
    "Condition": [
        r"\bcondition\b", r"\blooks?\b", r"\blooked\b", r"\bappears?\b",
        r"\bappeared\b", r"\bscratch", r"\bdents?\b", r"\bdented\b",
        r"\bbrand new\b", r"\balmost new\b", r"\blike new\b", r"\bnew\b",
        r"\bused\b", r"\bworn\b", r"\bwear and tear\b",
    ],
    "Battery": [
        r"\bbatter", r"\bcharging\b", r"\bcharge\b", r"\bcharges\b",
        r"\bdrains?\b", r"\bdraining\b", r"\bbackup\b",
    ],
    "Performance": [
        r"\bperformance\b", r"\bperforms?\b", r"\bspeed\b", r"\bslow\b",
        r"\bslower\b", r"\bfast\b", r"\blag", r"\bhangs?\b", r"\bfreezes?\b",
        r"\bprocessor\b", r"\bcpu\b", r"\bram\b", r"\bmultitask",
    ],
    "Display": [
        r"\bdisplay\b", r"\bscreen\b", r"\bmonitor\b", r"\bresolution\b",
        r"\bpixel", r"\bbrightness\b", r"\btouchscreen\b",
    ],
    "Camera": [
        r"\bcamera\b", r"\bphoto\b", r"\bphotos\b", r"\bpicture quality\b",
        r"\bvideo quality\b", r"\blens\b",
    ],
    "Accessories": [
        r"\baccessor", r"\bcharger\b", r"\bcable\b", r"\bcables\b",
        r"\badapter\b", r"\bheadphone", r"\bearphone", r"\bmanual\b",
    ],
    "Packaging": [
        r"\bpackag", r"\bbox\b", r"\bboxed\b", r"\bwrapping\b",
        r"\bwrapped\b", r"\bsealed\b", r"\btampered\b",
    ],
    "Delivery": [
        r"\bdeliver", r"\bshipping\b", r"\bshipment\b", r"\barriv",
        r"\bon time\b", r"\bcourier\b",
    ],
    "Seller Service": [
        r"\bseller\b", r"\bservice\b", r"\bsupport\b", r"\bresponsive\b",
        r"\bunresponsive\b", r"\bcommunication\b", r"\bstaff\b",
    ],
    "Return/Refund": [
        r"\breturn\b", r"\breturns\b", r"\breturned\b", r"\brefund",
        r"\breplacement\b", r"\bmoney back\b", r"\brma\b",
    ],
    "Price/Value": [
        r"\bprice\b", r"\bpricing\b", r"\bvalue\b", r"\bcost\b",
        r"\baffordab", r"\bbargain\b", r"\bworth\b", r"\bcheap\b",
        r"\bexpensive\b", r"\bbudget\b",
    ],
}

_COMPILED_ASPECTS: dict[str, list[re.Pattern]] = {
    aspect: [re.compile(pat, re.IGNORECASE) for pat in patterns]
    for aspect, patterns in ASPECT_KEYWORDS.items()
}

# Clause boundaries: conjunctions and punctuation that usually separate
# independent opinions inside one review.
_CLAUSE_SPLIT_RE = re.compile(
    r"\bbut\b|\bhowever\b|\balthough\b|\bthough\b|\bwhile\b|\band\b|[,;:.!?]",
    re.IGNORECASE,
)

# Fallback HF model: 3-class sentiment head (negative / neutral / positive).
DEFAULT_MODEL_ID = "cardiffnlp/twitter-roberta-base-sentiment-latest"

# A fine-tuned checkpoint dropped here is picked up automatically.
LOCAL_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models", "bert_model",
)

_NAME_MAP = {
    "positive": "Positive", "neutral": "Neutral", "negative": "Negative",
    "pos": "Positive", "neu": "Neutral", "neg": "Negative",
}
_INDEX_MAP = {0: "Negative", 1: "Neutral", 2: "Positive"}


def _split_clauses(text: str) -> list[str]:
    """Split a review into opinion-bearing clauses."""
    clauses = [c.strip() for c in _CLAUSE_SPLIT_RE.split(text)]
    return [c for c in clauses if len(c) >= 3]


def _detect_aspects(text: str) -> list[str]:
    """Return the aspects whose keywords appear in text (vocab order)."""
    return [
        aspect for aspect, patterns in _COMPILED_ASPECTS.items()
        if any(p.search(text) for p in patterns)
    ]


def _normalize_label(label: str) -> Optional[str]:
    """Map raw model labels (names, LABEL_x, 1-5 stars) onto our 3 classes."""
    low = label.strip().lower()
    if low in _NAME_MAP:
        return _NAME_MAP[low]
    m = re.fullmatch(r"label_(\d+)", low)
    if m:  # index-based head: assume 0=Negative, 1=Neutral, 2=Positive
        return _INDEX_MAP.get(int(m.group(1)))
    m = re.fullmatch(r"(\d+) stars?", low)
    if m:  # 5-star heads (e.g. nlptown): fold into three classes
        stars = int(m.group(1))
        return "Negative" if stars <= 2 else "Neutral" if stars == 3 else "Positive"
    return None


class ABSAEngine:
    """Keyword aspect detection + BERT span-level sentiment."""

    def __init__(self, model_id: Optional[str] = None):
        self.model_id = model_id or DEFAULT_MODEL_ID
        self.is_available = False
        self.load_error: Optional[str] = None
        self._pipe = None
        self._load_model()

    def _load_model(self) -> None:
        """Load a local fine-tuned checkpoint if present, else the HF model."""
        try:
            from transformers import pipeline

            source = self.model_id
            if os.path.isfile(os.path.join(LOCAL_MODEL_DIR, "config.json")):
                source = LOCAL_MODEL_DIR
            self._pipe = pipeline(
                "text-classification",
                model=source,
                top_k=None,
                truncation=True,
                max_length=512,
            )
            self.is_available = True
        except Exception as exc:  # surfaced as a friendly message in the UI
            self.load_error = f"{type(exc).__name__}: {exc}"
            self.is_available = False

    # --- sentiment ---
    def predict_sentiment(self, text: str) -> tuple[str, float]:
        """Classify a span as Positive / Neutral / Negative with confidence."""
        if not self.is_available:
            raise RuntimeError(self.load_error or "Sentiment model unavailable")
        outputs = self._pipe(text)
        scores = outputs[0] if outputs and isinstance(outputs[0], list) else outputs
        best_label, best_score = "Neutral", 0.0
        for item in scores:
            label = _normalize_label(item["label"])
            if label is not None and item["score"] >= best_score:
                best_label, best_score = label, float(item["score"])
        return best_label, round(best_score, 4)

    # --- aspects ---
    def extract_aspects(self, text: str) -> list[str]:
        """Aspects mentioned anywhere in the review."""
        return _detect_aspects(text)

    def analyze_review(self, text: str) -> list[dict]:
        """Per-aspect sentiment for a single review.

        Each clause is classified once and its sentiment is attributed to
        every aspect mentioned in that clause, so contrasting clauses keep
        their own polarity. The first mention of an aspect wins.
        """
        text = (text or "").strip()
        if not text:
            return []

        results: list[dict] = []
        seen: set[str] = set()
        for clause in _split_clauses(text):
            aspects = _detect_aspects(clause)
            if not aspects:
                continue
            sentiment, confidence = self.predict_sentiment(clause)
            for aspect in aspects:
                if aspect in seen:
                    continue
                seen.add(aspect)
                results.append({
                    "aspect": aspect,
                    "sentiment": sentiment,
                    "confidence": confidence,
                })

        if not results:  # no keyword hit: fall back to whole-review sentiment
            aspects = _detect_aspects(text) or ["Overall"]
            sentiment, confidence = self.predict_sentiment(text)
            results = [
                {"aspect": a, "sentiment": sentiment, "confidence": confidence}
                for a in aspects
            ]
        return results

    def overall_sentiment(self, text: str) -> tuple[str, float]:
        """Majority vote over aspect sentiments (ties broken by confidence)."""
        results = self.analyze_review(text)
        if not results:
            return self.predict_sentiment(text)
        votes: dict[str, list[float]] = {}
        for r in results:
            votes.setdefault(r["sentiment"], []).append(r["confidence"])
        label = max(
            votes,
            key=lambda k: (len(votes[k]), sum(votes[k]) / len(votes[k])),
        )
        return label, round(sum(votes[label]) / len(votes[label]), 4)

    # --- dataset level ---
    def run_absa(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run ABSA over a cleaned reviews DataFrame.

        Returns one row per (review, aspect) using the schema of
        data/processed/absa_results.csv.
        """
        rows = []
        for _, row in df.iterrows():
            for ar in self.analyze_review(str(row["review_text"])):
                rows.append({
                    "review_id": row.get("review_id"),
                    "category": row.get("category"),
                    "product_name": row.get("product_name", "Unknown"),
                    "aspect": ar["aspect"],
                    "sentiment": ar["sentiment"],
                    "confidence": ar["confidence"],
                    "platform": row.get("platform"),
                    "country": row.get("country"),
                    "review_date": row.get("review_date"),
                })
        return pd.DataFrame(rows)