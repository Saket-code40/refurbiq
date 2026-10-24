import { useState } from "react";

const STREAMLIT_URL =
  import.meta.env.VITE_STREAMLIT_URL || "http://localhost:8501";

export default function LiveDemo() {
  const [loaded, setLoaded] = useState(false);
  const embedSrc = `${STREAMLIT_URL}?embed=true`;

  return (
    <section id="live-demo" className="py-20 bg-white/60">
      <div className="max-w-6xl mx-auto px-4">
        <h2 className="font-serif text-3xl sm:text-4xl text-navy font-bold text-center mb-4">
          Live demo
        </h2>
        <p className="text-center text-ink/70 max-w-2xl mx-auto mb-10">
          The full Streamlit application: review upload, single-review
          analysis, analytics dashboard, platform comparison and explained
          recommendations.
        </p>

        <div className="card overflow-hidden">
          <div className="relative">
            {!loaded && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-pale z-10">
                <div
                  role="status"
                  aria-label="Loading the RefurbIQ application"
                  className="h-12 w-12 rounded-full border-4 border-teal border-t-transparent animate-spin"
                />
                <p className="text-ink/70 text-sm">
                  Loading the Streamlit app… (first load can take a minute on
                  free hosting)
                </p>
              </div>
            )}
            <iframe
              src={embedSrc}
              title="RefurbIQ Streamlit application"
              onLoad={() => setLoaded(true)}
              className="w-full h-[80vh] min-h-[600px] border-0"
              loading="lazy"
            />
          </div>
        </div>

        <p className="text-center text-sm text-ink/70 mt-4">
          If the embedded view does not load,{" "}
          <a
            href={STREAMLIT_URL}
            target="_blank"
            rel="noreferrer"
            className="text-teal font-semibold underline underline-offset-2 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy"
          >
            open the app in a new tab
          </a>
          .
        </p>
      </div>
    </section>
  );
}