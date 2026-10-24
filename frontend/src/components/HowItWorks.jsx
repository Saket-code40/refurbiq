const STEPS = [
  {
    title: "Collect reviews",
    text: "Refurbished-electronics reviews across five Indian marketplaces: Cashify, Amazon Renewed, Flipkart Refurbished, OLX and Budli (bundled demonstration corpus).",
  },
  {
    title: "Detect nine aspects",
    text: "Keyword-based aspect detection maps every review onto the nine aspects of the refurbished purchase journey.",
  },
  {
    title: "Label sentiment",
    text: "Each detected mention carries its evidence phrase, labelled positive, neutral or negative — the phrase, not the whole review, is the unit of analysis.",
  },
  {
    title: "Train and compare models",
    text: "Logistic Regression, Random Forest, XGBoost, zero-shot RoBERTa and fine-tuned DistilBERT are evaluated on the same review-level 70/15/15 split (seed 42).",
  },
  {
    title: "Compare platforms",
    text: "Aspect sentiment feeds transparent weighted scores per platform, gated by HIGH/MEDIUM/LOW confidence levels.",
  },
];

const ASPECTS = [
  "Product condition",
  "Battery health",
  "Performance",
  "Price and value",
  "Packaging and delivery",
  "Repair and refurbishment quality",
  "Seller and customer service",
  "Returns and refunds",
  "Trust and authenticity",
];

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="py-20">
      <div className="max-w-6xl mx-auto px-4">
        <h2 className="font-serif text-3xl sm:text-4xl text-navy font-bold text-center mb-4">
          How it works
        </h2>
        <p className="text-center text-ink/70 max-w-2xl mx-auto mb-14">
          Five steps from raw reviews to platform comparison, all reproducible
          from the repository.
        </p>

        <ol className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
          {STEPS.map((step, i) => (
            <li key={step.title} className="card p-6 relative">
              <span
                aria-hidden="true"
                className="absolute -top-4 left-6 bg-teal text-white font-serif font-bold rounded-full h-8 w-8 flex items-center justify-center"
              >
                {i + 1}
              </span>
              <h3 className="font-serif text-lg text-navy font-bold mt-3 mb-2">
                {step.title}
              </h3>
              <p className="text-sm text-ink/80">{step.text}</p>
            </li>
          ))}
        </ol>

        <div className="mt-14 text-center">
          <h3 className="font-serif text-xl text-navy font-bold mb-5">
            The nine aspects of the refurbished purchase journey
          </h3>
          <ul className="flex flex-wrap justify-center gap-3 max-w-3xl mx-auto">
            {ASPECTS.map((aspect) => (
              <li key={aspect} className="chip">
                {aspect}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}