import { useEffect, useState } from "react";
import Navbar from "./components/Navbar.jsx";
import Hero from "./components/Hero.jsx";
import HowItWorks from "./components/HowItWorks.jsx";
import LiveDemo from "./components/LiveDemo.jsx";
import Results from "./components/Results.jsx";
import Methodology from "./components/Methodology.jsx";
import Footer from "./components/Footer.jsx";

// JSON files produced by frontend/scripts/export_data.py — every number on
// the site comes from the project's computed outputs, never typed by hand.
const DATA_FILES = ["stats", "models", "aspect_sentiment", "heatmap"];

export default function App() {
  const [data, setData] = useState(null);

  useEffect(() => {
    const base = import.meta.env.BASE_URL;
    Promise.all(
      DATA_FILES.map((name) =>
        fetch(`${base}data/${name}.json`).then((r) => {
          if (!r.ok) throw new Error(`${name}.json: ${r.status}`);
          return r.json();
        })
      )
    )
      .then(([stats, models, aspectSentiment, heatmap]) =>
        setData({ stats, models, aspectSentiment, heatmap })
      )
      .catch((err) => setData({ error: String(err) }));
  }, []);

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-pale">
        <p className="font-serif text-lg text-navy">Loading project data…</p>
      </div>
    );
  }

  if (data.error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-pale px-4">
        <div className="card p-8 max-w-lg text-center">
          <h1 className="font-serif text-2xl text-navy mb-3">
            Data files not found
          </h1>
          <p className="text-ink mb-2">
            The site needs the exported JSON files under{" "}
            <code className="bg-pale px-1 rounded">frontend/public/data/</code>.
          </p>
          <p className="text-ink text-sm">
            Run{" "}
            <code className="bg-pale px-1 rounded">
              python frontend/scripts/export_data.py
            </code>{" "}
            and reload. ({data.error})
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Navbar />
      <main>
        <Hero stats={data.stats} />
        <HowItWorks />
        <LiveDemo />
        <Results
          models={data.models}
          aspectSentiment={data.aspectSentiment}
          heatmap={data.heatmap}
        />
        <Methodology />
      </main>
      <Footer />
    </div>
  );
}