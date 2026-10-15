"""Aspect-Based Sentiment Analysis engine.

V0.1 combines two deliberately simple pieces:

1. Aspect identification via a controlled keyword vocabulary
   (``ABSAEngine.extract_aspects``) — easy to swap for a fine-tuned
   aspect-extraction model later.
2. Whole-review sentiment classification with a BERT-family model from
   Hugging Face. A local fine-tuned checkpoint in ``models/bert_model/``
   is preferred when present.

Honesty note: this is not full joint ABSA — sentiment is scored on the
whole review, not on aspect-specific spans.
"""

from __future__ import annotations

import os

import pandas as pd

ASPECT_KEYWORDS = {
    "Condition": [
        "condition", "looks new", "like new", "almost new", "as new",
        "scratches", "scratch", "dents", "dent", "marks", "worn",
        "refurbished", "appearance", "cosmetic", "body",
    ],
    "Battery": [
        "battery", "charge", "charging", "battery life", "battery backup",
        "drains", "drain", "holds charge",
    ],
    "Performance": [
        "performance", "speed", "slow", "lag", "laggy", "hangs", "freeze",
        "freezes", "smooth", "fast", "heating", "overheats", "processor",
        "ram", "multitasking",
    ],
    "Display": [
        "display", "screen", "brightness", "pixels", "dead pixel",
        "touchscreen", "touch", "amoled", "lcd",
    ],
    "Camera": [
        "camera", "photos", "photo", "pictures", "picture", "selfie",
        "lens", "video quality",
    ],
    "Accessories": [
        "charger", "cable", "adapter", "earphones", "headphones",
        "accessories", "accessory", "case", "cover", "manual",
    ],
    "Packaging": [
        "packaging", "packed", "box", "unboxing", "bubble wrap", "wrapper",
    ],
    "Delivery": [
        "delivery", "shipping", "shipped", "arrived", "courier", "dispatch",
        "transit", "on time", "late delivery",
    ],
    "Seller Service": [
        "seller", "customer service", "support", "helpful", "responsive",
        "communication", "warranty",
    ],
    "Return/Refund": [
        "return", "returned", "refund", "replacement", "exchange",
        "money back",
    ],
    "Price/Value": [
        "price", "value", "worth", "deal", "expensive", "cheap",
        "value for money", "affordable", "cost",
    ],
    "Repair/Refurbishment": [
        "refurbishment", "refurb", "repaired", "repair work", "serviced",
        "third-party parts", "non-original parts", "refurbished to perfection",
        "factory-fresh", "certified refurbishment", "gaps in the body",
        "loose screws", "screen replacement",
    ],
    "Trust/Authenticity": [
        "authentic", "genuine", "original", "fake", "counterfeit",
        "trustworthy", "trust", "scam", "legit", "verified", "imei",
        "serial number", "tampered", "warranty card", "documents",
        "certified pre-owned",
    ],
}

ASPECTS = list(ASPECT_KEYWORDS)

POSITIVE_LABELS = {"positive", "label_2", "5 stars", "4 stars", "pos"}
NEGATIVE_LABELS = {"negative", "label_0", "1 star", "2 stars", "neg"}

# Pipeline tries a local fine-tuned checkpoint first, then a multilingual
# sentiment model, then falls back to a lightweight lexicon scorer.
LOCAL_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "bert_model",
)
DEFAULT_MODEL = "nlptown/bert-base-multilingual-uncased-sentiment"
FALLBACK_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"

_FALLBACK_LEXICON = {
    "positive": [
        "good", "great", "excellent", "amazing", "perfect", "love", "loved",
        "best", "awesome", "fantastic", "happy", "satisfied", "impressed",
        "smooth", "fast", "new", "recommend", "recommended", "worth",
        "sturdy", "promptly", "beautifully", "flawless", "brilliant",
        "crisp", "genuine", "helpful", "superb", "nice",
    ],
    "negative": [
        "bad", "poor", "terrible", "awful", "horrible", "worst", "hate",
        "disappointed", "disappointing", "waste", "broken", "defective",
        "damaged", "fake", "slow", "laggy", "lag", "drains", "drain",
        "scratches", "scratched", "scam", "useless", "overheats", "dead",
        "cracked", "cheap", "flimsy", "rude", "late", "never", "failed",
        "refuse", "refused", "mediocre", "average", "issues", "problem",
    ],
}


class ABSAEngine:
    """Aspect extraction + sentiment classification for product reviews."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name
        self.pipeline = None
        self.is_available = False
        self.load_error: str | None = None
        self._load_model()

    # --- Model loading ---
    def _load_model(self) -> None:
        """Try local checkpoint, then the default HF model, then a fallback.

        Failure never raises: ``is_available`` stays False and the UI shows
        ``load_error`` instead.
        """
        try:
            from transformers import pipeline as hf_pipeline
        except Exception as exc:  # transformers (or torch) not installed
            self.load_error = f"transformers unavailable: {exc}"
            return

        candidates = []
        if self.model_name:
            candidates.append(self.model_name)
        elif os.path.isdir(LOCAL_MODEL_DIR) and os.listdir(LOCAL_MODEL_DIR):
            candidates.append(LOCAL_MODEL_DIR)
        candidates.append(DEFAULT_MODEL)
        candidates.append(FALLBACK_MODEL)

        for candidate in candidates:
            try:
                self.pipeline = hf_pipeline(
                    "text-classification",
                    model=candidate,
                    top_k=None,
                    truncation=True,
                )
                self.is_available = True
                self.model_name = candidate
                return
            except Exception as exc:
                self.load_error = f"{candidate}: {exc}"

    # --- Aspect identification ---
    def extract_aspects(self, text: str) -> list[str]:
        """Detect mentioned aspects via keyword matching (V0.1 mechanism)."""
        lowered = text.lower()
        found = [
            aspect
            for aspect, keywords in ASPECT_KEYWORDS.items()
            if any(kw in lowered for kw in keywords)
        ]
        return found or ["General"]

    # --- Sentiment classification ---
    def _map_label(self, label: str) -> str:
        """Map a model-specific label onto Positive/Neutral/Negative."""
        normalized = label.strip().lower()
        if normalized in POSITIVE_LABELS:
            return "Positive"
        if normalized in NEGATIVE_LABELS:
            return "Negative"
        return "Neutral"

    def _fallback_score(self, text: str) -> tuple[str, float]:
        """Lexicon-based sentiment used when no neural model is available."""
        lowered = text.lower()
        pos = sum(lowered.count(word) for word in _FALLBACK_LEXICON["positive"])
        neg = sum(lowered.count(word) for word in _FALLBACK_LEXICON["negative"])
        total = pos + neg
        if total == 0:
            return "Neutral", 0.5
        confidence = max(pos, neg) / total
        sentiment = "Positive" if pos >= neg else "Negative"
        return sentiment, round(min(0.5 + confidence / 2, 0.99), 2)

    def overall_sentiment(self, text: str) -> tuple[str, float]:
        """Classify whole-review sentiment; returns (label, confidence)."""
        if not self.is_available or self.pipeline is None:
            return self._fallback_score(text)
        try:
            scores = self.pipeline(text)[0]
            best = max(scores, key=lambda s: s["score"])
            return self._map_label(best["label"]), float(best["score"])
        except Exception:
            return self._fallback_score(text)

    # --- Review-level API ---
    def analyze_review(self, text: str) -> list[dict]:
        """Return one sentiment record per detected aspect for a review."""
        sentiment, confidence = self.overall_sentiment(text)
        return [
            {"aspect": aspect, "sentiment": sentiment, "confidence": confidence}
            for aspect in self.extract_aspects(text)
        ]

    # --- Batch API ---
    def run_absa(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run ABSA over a cleaned DataFrame.

        Produces one row per review–aspect pair, carrying through optional
        metadata columns when present.
        """
        records = []
        for _, row in df.iterrows():
            text = str(row["review_text"])
            sentiment, confidence = self.overall_sentiment(text)
            for aspect in self.extract_aspects(text):
                records.append(
                    {
                        "review_id": row.get("review_id"),
                        "review_text": text,
                        "aspect": aspect,
                        "sentiment": sentiment,
                        "confidence": round(float(confidence), 4),
                        "category": row.get("category"),
                        "product_name": row.get("product_name"),
                        "brand": row.get("brand"),
                        "rating": row.get("rating"),
                        "platform": row.get("platform"),
                        "seller": row.get("seller"),
                        "country": row.get("country"),
                        "review_date": row.get("review_date"),
                    }
                )
        return pd.DataFrame(records)
