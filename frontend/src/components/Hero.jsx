function StatCard({ label, value }) {
  return (
    <div className="card px-6 py-6 text-center">
      <p className="font-serif text-2xl sm:text-3xl text-navy font-bold">
        {value}
      </p>
      <p className="text-ink/80 text-sm mt-2">{label}</p>
    </div>
  );
}

export default function Hero({ stats }) {
  return (
    <section
      id="home"
      className="bg-gradient-to-b from-navy to-teal text-white"
    >
      <div className="max-w-6xl mx-auto px-4 py-20 sm:py-28 text-center">
        <p className="uppercase tracking-widest text-white/70 text-sm mb-4">
          Project Based Learning 3
        </p>
        <h1 className="font-serif text-4xl sm:text-5xl font-bold mb-4">
          RefurbIQ
        </h1>
        <p className="font-serif text-xl sm:text-2xl text-white/90 max-w-3xl mx-auto mb-6">
          Aspect-Based Sentiment Analysis of Refurbished Electronics Across
          Indian Marketplaces
        </p>
        <p className="max-w-2xl mx-auto text-white/80 mb-10">
          Reviews are split into nine purchase-journey aspects, each evidence
          phrase is labelled positive, neutral or negative, and five sentiment
          models are compared on a leak-free protocol — {stats.annotations}{" "}
          aspect annotations in the demonstration corpus.
        </p>
        <a href="#live-demo" className="btn-primary">
          Try the live demo
        </a>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mt-16 text-ink">
          <StatCard
            label="Reviews in demo corpus"
            value={stats.demoReviews}
          />
          <StatCard
            label="Platforms compared"
            value={stats.platformsCompared}
          />
          <StatCard label="Best model" value={stats.bestModel} />
        </div>
        <p className="text-white/60 text-xs mt-6 max-w-2xl mx-auto">
          {stats.provenance}
        </p>
      </div>
    </section>
  );
}