# RefurbIQ

**Refurbished Product Review Intelligence** — an AI-powered application that analyzes reviews of refurbished electronic products using BERT-based Aspect-Based Sentiment Analysis (ABSA) and produces transparent, evidence-based **buying recommendations** across Indian refurbished-product platforms.

RefurbIQ doesn't just classify reviews as positive or negative. It identifies **what aspect** a customer is talking about (battery, display, delivery, trust, etc.), **how they feel** about it, and then answers the question buyers actually ask: **"Where should I buy this refurbished product?"**

---

## 1. Project Purpose

Buyers of refurbished electronics rely heavily on reviews, but reading hundreds of them across multiple platforms is impractical. RefurbIQ automatically:

- Identifies the product aspect being discussed (13 aspects: Condition, Battery, Performance, Display, Camera, Accessories, Packaging, Delivery, Seller Service, Return/Refund, Price/Value, Repair/Refurbishment, Trust/Authenticity)
- Classifies the sentiment toward each aspect (Positive / Neutral / Negative)
- Measures how frequently each aspect appears and which aspects generate the most negative sentiment
- Compares platforms (Cashify, Amazon Renewed, Flipkart Refurbished, OLX, Budli) using a multi-factor recommendation score
- Explains *why* one platform ranks above another
- Generates simple, data-driven insights

Supported categories: **Refurbished Phones**, **Refurbished Laptops**, and **Refurbished DSLR Cameras**. Country scope: **India**.

---

## 2. Architecture

```
Review CSV
   ↓
Preprocessing  (src/preprocessing.py)
   ↓
Aspect Identification  (keyword vocabulary — src/absa.py)
   ↓
BERT Sentiment Classification  (Hugging Face Transformers)
   ↓
ABSA Results  (data/processed/absa_results.csv)
   ↓
Analytics  (src/analytics.py)
   ↓
Recommendation Engine  (src/recommendation.py)
   ↓
Streamlit Dashboard + Plotly Charts  (app.py)
```

The ML layer and the recommendation engine are strictly separated: the engine consumes validated aspect/sentiment results only — never raw model confidences. The Streamlit app calls reusable functions from `src/` and contains no ML logic.

---

## 3. Dataset Format

Place a CSV in `data/raw/` (a sample `reviews.csv` with 1,500 reviews is included). Supported columns:

| Column | Required | Example |
| --- | --- | --- |
| `review_id` | no | 1 |
| `review_text` | **yes** | "The phone looks almost new but the battery drains quickly" |
| `category` | **yes** | Phone / Laptop / Camera |
| `product_name` | no | iPhone 13 |
| `brand` | no | Apple |
| `rating` | no | 4 |
| `platform` | no | Cashify |
| `seller` | no | Cashify Certified |
| `country` | no | India |
| `review_date` | no | 2026-09-20 |

The app works even when optional columns are missing — related charts and recommendation features are hidden or degraded gracefully. When individual `seller` data is present, seller-level sentiment is shown separately and is never inferred from platform-level sentiment.

> The bundled dataset is **synthetic sample data** for demonstration. Recommendations shown by the app are based on analyzed review evidence, not on live marketplace data.

---

## 4. Installation

```bash
cd refurbiq   # or wherever you cloned the project

python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# CPU-only PyTorch keeps the install light; drop the index flag if you have a GPU
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

> The sentiment model is downloaded automatically from Hugging Face on first run, so an internet connection is needed once. A fine-tuned checkpoint placed in `models/bert_model/` is picked up automatically instead.

---

## 5. Running the Application

```bash
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

The app has eight sections (tabs):

- **Overview** — KPI cards + key insights
- **Upload Reviews** — upload a CSV, see a summary, click *Analyze Reviews*
- **Review Analyzer** — type any single review and get instant aspect-level sentiment
- **Analytics Dashboard** — interactive Plotly charts (sentiment distribution, aspect frequency, sentiment by aspect/category/platform/country) plus automated insights
- **Compare Platforms** — select a product and compare platforms on sentiment %, review volume, and score; includes "Best for X" quick filters (Best Battery, Best Value, Best Customer Service, Most Trusted, …)
- **Best Place to Buy** — recommendation card with confidence level, supporting factors, and things to check before purchasing
- **Explain Recommendation** — factor-by-factor breakdown of why one platform ranks above another
- **Methodology** — transparent scoring formula with configurable weights and minimum-review threshold

---

## 6. ML Pipeline

1. **Preprocessing** — loads the CSV, validates required columns, removes empty and duplicate reviews, fills missing values. Text is kept in natural language (no stemming/aggressive stopword removal) because BERT expects natural sentences.
2. **Aspect identification** — a controlled keyword vocabulary detects which of the 13 aspects are mentioned. Isolated in `ABSAEngine.extract_aspects()` so it can be replaced by a fine-tuned aspect-extraction model later.
3. **Sentiment classification** — a BERT-family model classifies sentiment, mapped to Positive / Neutral / Negative with a confidence score.
4. **Analytics** — aggregates aspect frequencies and sentiment distributions, then generates insights strictly from the computed data.
5. **Recommendation engine** — consumes the validated ABSA results and produces platform scores.

### Recommendation methodology

For each product × platform combination the engine computes sub-scores (0–10) from sentiment distributions:

```
sub-score = (positive% × 1.0 + neutral% × 0.5 + negative% × 0.0) × 10

Overall Score =
    Sentiment Score          × 0.25
  + Product Quality Score    × 0.25   (Condition, Battery, Performance, Display, Camera)
  + Service Score            × 0.15   (Seller Service, Delivery, Packaging)
  + Value-for-Money Score    × 0.15   (Price/Value)
  + Trust Score              × 0.10   (Trust/Authenticity, Repair/Refurbishment)
  + Return/Refund Score      × 0.10   (Return/Refund)
```

Weights and the minimum-review threshold are configurable in the **Methodology** tab. Platforms with fewer than the threshold of unique reviews are excluded from ranking — the app never claims a winner on a tiny sample.

Confidence levels:

- **HIGH** — large review sample with consistent sentiment
- **MEDIUM** — moderate sample or some conflicting evidence
- **LOW** — small sample; no recommendation is issued

---

## 7. Current Limitations

- Aspect identification is keyword-based, not a trained sequence-labeling model
- Sentiment is classified on the full review rather than on aspect-specific text spans
- Only 3-class sentiment (no fine-grained ratings prediction)
- The bundled dataset is synthetic and for demonstration only — no live marketplace data is used
- Recommendations reflect historical review sentiment, not current prices, stock, or warranty terms
- No authentication, payments, database, or deployment infrastructure

---

## 8. Future Improvements

- Fine-tuned aspect extraction model to replace keyword matching
- Span-level sentiment classification per aspect
- TF-IDF baselines (Logistic Regression, Naive Bayes, Linear SVM) for model comparison
- LLM second-stage analysis for ambiguous/mixed reviews
- More product categories and marketplace integrations where permitted
- Refurbished Product Risk Index, product comparison, buyer inspection checklist
- Backend: Streamlit → FastAPI → Python ML Engine → PostgreSQL

---

## Project Structure

```
refurbiq/
├── data/
│   ├── raw/
│   │   └── reviews.csv            # sample input dataset (1,500 reviews)
│   └── processed/
│       └── absa_results.csv       # generated by analysis
├── models/
│   └── bert_model/                # optional local fine-tuned model
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_baseline.ipynb          # (planned TF-IDF baselines)
│   └── 03_bert_absa.ipynb
├── src/
│   ├── preprocessing.py           # CSV loading & cleaning
│   ├── absa.py                    # aspect detection + BERT sentiment
│   ├── analytics.py               # statistics & insights
│   └── recommendation.py          # multi-factor platform recommendation engine
├── app.py                         # Streamlit UI (8 tabs)
├── requirements.txt
└── README.md
```