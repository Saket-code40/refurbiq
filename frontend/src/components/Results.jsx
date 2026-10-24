import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// Palette shared with the report figures: positive green, neutral grey,
// negative crimson.
const COLORS = { positive: "#2E7D32", neutral: "#9E9E9E", negative: "#B03A5B" };

// Short display names for chart axes — labels only, numbers are unchanged.
const SHORT_MODEL = {
  "Logistic Regression": "Logistic Regression",
  "Random Forest": "Random Forest",
  XGBoost: "XGBoost",
  "BERT-based model (zero-shot)": "BERT (zero-shot)",
  "BERT-based model (fine-tuned DistilBERT)": "BERT (fine-tuned)",
};

const pct = (v) => `${(v * 100).toFixed(1)}%`;

function ChartCard({ title, note, children }) {
  return (
    <div className="card p-6 sm:p-8">
      <h3 className="font-serif text-xl text-navy font-bold mb-1">{title}</h3>
      <div role="img" aria-label={title}>
        {children}
      </div>
      <p className="text-xs text-ink/60 mt-4">{note}</p>
    </div>
  );
}

function ModelChart({ models }) {
  const rows = models.models.map((m) => ({
    ...m,
    model: SHORT_MODEL[m.model] ?? m.model,
  }));
  return (
    <ChartCard
      title="Model comparison on the held-out test split"
      note="Accuracy, macro F1 and neutral-class recall for all five models, read from research/tables/table3 and table4. Test split: 537 annotations, review-level stratified partition, seed 42."
    >
      <div className="h-96">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 10, right: 10, bottom: 10, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#26323F22" />
            <XAxis
              dataKey="model"
              tick={{ fontSize: 12, fill: "#26323F" }}
              interval={0}
              angle={-15}
              textAnchor="end"
              height={60}
            />
            <YAxis
              domain={[0, 1]}
              tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
              tick={{ fontSize: 12, fill: "#26323F" }}
            />
            <Tooltip formatter={(v) => pct(v)} />
            <Legend />
            <Bar dataKey="accuracy" name="Accuracy" fill="#1F6F78" radius={[4, 4, 0, 0]} />
            <Bar dataKey="macroF1" name="Macro F1" fill="#1F3864" radius={[4, 4, 0, 0]} />
            <Bar dataKey="neutralRecall" name="Neutral recall" fill="#B03A5B" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}

function AspectChart({ aspectSentiment }) {
  return (
    <ChartCard
      title="Sentiment mix by aspect"
      note="Percentage of positive, neutral and negative mentions per aspect, read from research/tables/table5_sentiment_by_aspect.csv. Denominators are mention counts on the demonstration corpus."
    >
      <div className="h-[28rem]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={aspectSentiment.aspects}
            layout="vertical"
            margin={{ top: 10, right: 20, bottom: 10, left: 10 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#26323F22" />
            <XAxis
              type="number"
              domain={[0, 100]}
              tickFormatter={(v) => `${v}%`}
              tick={{ fontSize: 12, fill: "#26323F" }}
            />
            <YAxis
              type="category"
              dataKey="aspect"
              width={180}
              tick={{ fontSize: 12, fill: "#26323F" }}
            />
            <Tooltip formatter={(v) => `${v}%`} />
            <Legend />
            <Bar dataKey="positive" name="Positive" stackId="a" fill={COLORS.positive} />
            <Bar dataKey="neutral" name="Neutral" stackId="a" fill={COLORS.neutral} />
            <Bar dataKey="negative" name="Negative" stackId="a" fill={COLORS.negative} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}

// Linear interpolation between pale blue and crimson by negative share.
function lerpColor(a, b, t) {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  return `rgb(${pa.map((v, i) => Math.round(v + (pb[i] - v) * t)).join(",")})`;
}

function Heatmap({ heatmap }) {
  const shares = heatmap.cells.map((c) => c.negativeShare);
  const min = Math.min(...shares);
  const max = Math.max(...shares);
  const byCell = new Map(
    heatmap.cells.map((c) => [`${c.platform}|${c.aspect}`, c.negativeShare])
  );

  return (
    <div className="card p-6 sm:p-8">
      <h3 className="font-serif text-xl text-navy font-bold mb-1">
        Platform × aspect negative-share heatmap
      </h3>
      <div className="overflow-x-auto" role="img" aria-label="Heatmap of negative mention share per platform and aspect">
        <table className="mt-4 border-separate border-spacing-1 min-w-[760px]">
          <thead>
            <tr>
              <th className="text-left text-sm text-ink/70 font-medium pr-2">
                Platform
              </th>
              {heatmap.aspects.map((aspect) => (
                <th
                  key={aspect}
                  scope="col"
                  className="text-xs text-ink/70 font-medium align-bottom px-1"
                >
                  <span className="inline-block [writing-mode:vertical-rl] rotate-180 whitespace-nowrap max-h-36">
                    {aspect}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {heatmap.platforms.map((platform) => (
              <tr key={platform}>
                <th scope="row" className="text-left text-sm text-ink font-medium pr-2 whitespace-nowrap">
                  {platform}
                </th>
                {heatmap.aspects.map((aspect) => {
                  const share = byCell.get(`${platform}|${aspect}`);
                  if (share === undefined) {
                    return (
                      <td key={aspect} className="h-10 w-14 bg-pale text-center text-xs text-ink/50">
                        N/A
                      </td>
                    );
                  }
                  const t = max === min ? 0 : (share - min) / (max - min);
                  const dark = t > 0.55;
                  return (
                    <td
                      key={aspect}
                      className="h-10 w-14 text-center text-xs font-semibold rounded"
                      style={{
                        backgroundColor: lerpColor("#E6EFF4", "#B03A5B", t),
                        color: dark ? "#ffffff" : "#26323F",
                      }}
                      title={`${platform} — ${aspect}: ${(share * 100).toFixed(1)}% negative mentions`}
                    >
                      {(share * 100).toFixed(0)}%
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-3 mt-5 text-xs text-ink/70">
        <span>{pct(min)} negative</span>
        <span
          aria-hidden="true"
          className="h-3 w-40 rounded-full"
          style={{
            background: "linear-gradient(to right, #E6EFF4, #B03A5B)",
          }}
        />
        <span>{pct(max)} negative</span>
      </div>
      <p className="text-xs text-ink/60 mt-4">
        Share of negative mentions per platform and aspect, computed from
        research/data/aspect_annotations.csv. These are demonstration-corpus
        observations only — they are not findings about the real marketplaces.
      </p>
    </div>
  );
}

export default function Results({ models, aspectSentiment, heatmap }) {
  return (
    <section id="results" className="py-20">
      <div className="max-w-6xl mx-auto px-4">
        <h2 className="font-serif text-3xl sm:text-4xl text-navy font-bold text-center mb-4">
          Results
        </h2>
        <p className="text-center text-ink/70 max-w-2xl mx-auto mb-12">
          Every figure below is loaded from the project's computed outputs —
          nothing is hand-typed, and every value can be regenerated from the
          repository with seed 42.
        </p>
        <div className="space-y-10">
          <ModelChart models={models} />
          <AspectChart aspectSentiment={aspectSentiment} />
          <Heatmap heatmap={heatmap} />
        </div>
      </div>
    </section>
  );
}