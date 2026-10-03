# RefurbIQ

**Refurbished Product Review Intelligence** — an AI-powered application that analyzes reviews of refurbished electronic products using BERT-based Aspect-Based Sentiment Analysis (ABSA).

RefurbIQ doesn't just classify reviews as positive or negative. It identifies **what aspect** a customer is talking about (battery, display, delivery, etc.), **how they feel** about it, and surfaces **actionable insights** across the whole dataset.

---

## 1. Project Purpose

Buyers of refurbished electronics rely heavily on reviews, but reading hundreds of them is impractical. RefurbIQ automatically:

- Identifies the product aspect being discussed (Condition, Battery, Performance, Display, Camera, Accessories, Packaging, Delivery, Seller Service, Return/Refund, Price/Value)
- Classifies the sentiment toward each aspect (Positive / Neutral / Negative)
- Measures how frequently each aspect appears
- Highlights which aspects generate the most negative sentiment
- Generates simple, data-driven insights

Supported categories (V0.1): **Refurbished Phones** and **Refurbished Laptops**.

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
Analytics & Insights  (src/analytics.py)
   ↓
Streamlit Dashboard + Plotly Charts  (app.py)
```

ML logic is fully separated from the UI. The Streamlit app only calls reusable functions from `src/`.

---

## 3. Dataset Format

Place a CSV in `data/raw/` (a sample `reviews.csv` is included). Supported columns:

| Column | Required | Example |
| --- | --- | --- |
| `review_id` | no | 1 |
| `review_text` | **yes** | "The phone looks almost new but the battery drains quickly" |
| `category` | **yes** | Phone / Laptop |
| `product_name` | no | iPhone 13 |
| `rating` | no | 3 |
| `platform` | no | Example Marketplace |
| `country` | no | India |
| `review_date` | no | 2026-09-20 |

The app works even when optional columns (country/platform/date) are missing — related charts are simply hidden.

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

> The sentiment model (`cardiffnlp/twitter-roberta-base-sentiment-latest`) is downloaded automatically from Hugging Face on first run, so an internet connection is needed once. A fine-tuned checkpoint placed in `models/bert_model/` is picked up automatically instead.

---

## 5. Running the Application

```bash
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

The app has four sections (tabs):

- **Overview** — KPI cards + key insights (uses the bundled sample data until you upload your own)
- **Upload Reviews** — upload a CSV, see a summary, click *Analyze Reviews*
- **Review Analyzer** — type any single review and get instant aspect-level sentiment
- **Analytics Dashboard** — interactive Plotly charts (sentiment distribution, aspect frequency, sentiment by aspect/category/platform/country) plus automated insights

---

## 6. ML Pipeline

1. **Preprocessing** — loads the CSV, validates required columns, removes empty and duplicate reviews, fills missing values. Text is kept in natural language (no stemming/aggressive stopword removal) because BERT expects natural sentences.
2. **Aspect identification** — a controlled keyword vocabulary detects which of the 11 aspects are mentioned. This is a deliberately simple V0.1 mechanism; it is isolated in `ABSAEngine.extract_aspects()` so it can be replaced by a fine-tuned aspect-extraction model later.
3. **Sentiment classification** — a BERT model (`bert-base-multilingual-uncased-sentiment`) classifies sentiment, mapped to Positive / Neutral / Negative with a confidence score. Uses GPU automatically if available.
4. **Analytics** — aggregates aspect frequencies and sentiment distributions, then generates insights strictly from the computed data.

> **Honesty note:** this is *not* full joint ABSA. It combines keyword-based aspect detection with whole-review BERT sentiment classification. A fine-tuned, span-level ABSA model is planned for a future version.

### Baseline comparison (planned notebooks)

A TF-IDF + Logistic Regression baseline is included in the roadmap (`notebooks/02_baseline.ipynb`) so the BERT model can be compared against traditional ML using accuracy, precision, recall, F1-score, and a confusion matrix.

---

## 7. Current Limitations

- Aspect identification is keyword-based, not a trained sequence-labeling model
- Sentiment is classified on the full review rather than on aspect-specific text spans
- Only 3-class sentiment (no fine-grained ratings prediction)
- Only Phones and Laptops categories
- No authentication, payments, database, or deployment infrastructure
- The bundled sample dataset is small (40 reviews) and for demonstration only

---

## 8. Future Improvements

- Fine-tuned aspect extraction model to replace keyword matching
- Span-level sentiment classification per aspect
- Fine-tuned BERT model on refurbished-product reviews
- TF-IDF + Logistic Regression baseline and model comparison
- More product categories (Cameras, etc.)
- Refurbished Product Risk Index and product comparison
- Buyer inspection checklist
- Marketplace integrations where permitted
- Country-level analysis, React frontend, user accounts
- Backend: Streamlit → FastAPI → Python ML Engine → PostgreSQL

---

## Project Structure

```
refurbiq/
├── data/
│   ├── raw/
│   │   └── reviews.csv            # sample input dataset
│   └── processed/
│       └── absa_results.csv       # generated by analysis
├── models/
│   └── bert_model/                # optional local fine-tuned model
├── notebooks/
│   ├── 01_data_exploration.ipynb  # (planned)
│   ├── 02_baseline.ipynb          # (planned)
│   └── 03_bert_absa.ipynb         # (planned)
├── src/
│   ├── preprocessing.py           # CSV loading & cleaning
│   ├── absa.py                    # aspect detection + BERT sentiment
│   └── analytics.py               # statistics & insights
├── app.py                         # Streamlit UI
├── requirements.txt
└── README.md
```