const REPO_URL = "https://github.com/Saket-code40/refurbiq";

export default function Methodology() {
  return (
    <section id="methodology" className="py-20 bg-white/60">
      <div className="max-w-4xl mx-auto px-4">
        <h2 className="font-serif text-3xl sm:text-4xl text-navy font-bold text-center mb-12">
          Methodology and limitations
        </h2>

        <div className="card p-6 sm:p-10 space-y-6 text-ink/90 leading-relaxed">
          <div>
            <h3 className="font-serif text-xl text-navy font-bold mb-2">
              Pipeline
            </h3>
            <p>
              Reviews are cleaned, then keyword-based aspect detection maps
              each mention onto one of nine aspects of the refurbished
              purchase journey. Sentiment is classified per evidence phrase —
              the span of text that supports the label — using three
              classical models on TF-IDF features (Logistic Regression,
              Random Forest, XGBoost) and two transformer configurations
              (zero-shot RoBERTa, fine-tuned DistilBERT). All five models are
              evaluated once on the same held-out test partition of a
              review-level stratified 70/15/15 split (seed 42), so no test
              example is used for model selection.
            </p>
          </div>

          <div>
            <h3 className="font-serif text-xl text-navy font-bold mb-2">
              Recommendations
            </h3>
            <p>
              Platform scores are weighted sums of six transparent sub-scores
              (overall sentiment, product quality, service, value, trust,
              returns), each computed from the sentiment distribution of the
              relevant aspect group. Platforms below the minimum review
              threshold are excluded from rankings, and confidence is reported
              as HIGH, MEDIUM or LOW. Recommendations are evidence about past
              review sentiment, never guarantees of product quality.
            </p>
          </div>

          <div>
            <h3 className="font-serif text-xl text-navy font-bold mb-2">
              Limitations
            </h3>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                The modelling corpus is a clearly labelled synthetic
                demonstration corpus; structured public reviews are currently
                unavailable for the five marketplaces, so platform-level
                results here are corpus observations, not verified marketplace
                findings.
              </li>
              <li>
                The neutral class is the hardest for every model; a separate
                run on 2,000 real Amazon reviews validates the pipeline
                against human star ratings.
              </li>
              <li>
                Aspect detection is keyword-based (an auditable V0.1 choice);
                a fine-tuned span extractor is future work.
              </li>
            </ul>
          </div>

          <div className="pt-2 text-center">
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="btn-primary"
            >
              View the source on GitHub
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}