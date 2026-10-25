import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const env = import.meta.env as Record<string, string | undefined>;
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

interface HumanPair {
  candidates: number;
  sim_vs_human: { directional_accuracy: number; spearman: number };
  human_vs_reality: { directional_accuracy: number; spearman: number };
}

interface Row {
  comparisons: number;
  directional_accuracy: number | null;
  spearman: number | null;
  top_1_hit_rate: number | null;
  sample_sufficient: boolean;
  sim_vs_random_delta: number | null;
  human: HumanPair | null;
  classification: string;
}

interface Checkpoint {
  generated_at: string;
  min_samples: number;
  experiments_scored: number;
  human_available: boolean;
  human_note: string;
  overall: Row;
  buckets: Record<string, Record<string, Row>>;
  classification_counts: Record<string, number>;
  outcome: string;
  recommendation: string;
  outcome_text: string;
}

const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);
const COLOR: Record<string, string> = {
  strong: "#1b5e20",
  mixed: "#a06000",
  weak: "#b00020",
  insufficient: "#555",
};

function RowTable({ rows }: { rows: Record<string, Row> }) {
  const entries = Object.entries(rows);
  if (entries.length === 0) return <p>No data.</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>bucket</th>
          <th>comparisons</th>
          <th>sim directional</th>
          <th>vs random</th>
          <th>sim vs human</th>
          <th>classification</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([key, row]) => (
          <tr key={key}>
            <td>{key}</td>
            <td>{row.comparisons}</td>
            <td>{pct(row.directional_accuracy)}</td>
            <td>{row.sim_vs_random_delta ?? "—"}</td>
            <td>{row.human ? pct(row.human.sim_vs_human.directional_accuracy) : "—"}</td>
            <td style={{ color: COLOR[row.classification] ?? "#333" }}>
              {row.classification}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Checkpoint() {
  const [data, setData] = useState<Checkpoint | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  useEffect(() => {
    fetch(`${ROOT}/api/checkpoint/preview`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setError("checkpoint failed"));
  }, []);

  const save = async () => {
    try {
      const res = await fetch(`${ROOT}/api/checkpoint`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(await res.text());
      const body = await res.json();
      setSaved(`saved checkpoint #${body.checkpoint_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "save failed");
    }
  };

  if (error) return <main style={{ padding: 24 }}>{error}</main>;
  if (!data) return <main style={{ padding: 24 }}>loading checkpoint…</main>;

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 1000 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link> ·{" "}
        <Link to="/reality-gap">Reality gap</Link>
      </p>
      <h1>Major research checkpoint</h1>
      <p>
        Is the simulated audience actually useful? Simulator vs random vs human
        judges across {data.experiments_scored} scored experiments.
      </p>
      <section
        style={{
          border: `2px solid ${COLOR[data.outcome] ?? "#333"}`,
          borderRadius: 8,
          padding: 12,
        }}
      >
        <h2 style={{ color: COLOR[data.outcome] ?? "#333" }}>
          {data.outcome.toUpperCase()} — {data.recommendation}
        </h2>
        <p>{data.outcome_text}</p>
        <button onClick={() => void save()}>save snapshot</button>
        {saved && <p>{saved}</p>}
      </section>

      <h2>Overall</h2>
      <p>
        {data.overall.comparisons} comparisons · minimum {data.min_samples} ·{" "}
        {data.human_available ? data.human_note : "human panel unavailable"}
      </p>
      <RowTable rows={{ overall: data.overall }} />

      {Object.entries(data.buckets).map(([dimension, rows]) => (
        <section key={dimension}>
          <h3>{dimension.replace("_", " ")}</h3>
          <RowTable rows={rows} />
        </section>
      ))}

      <p style={{ color: "#777" }}>
        Classifications: {Object.entries(data.classification_counts)
          .map(([k, v]) => `${k}=${v}`)
          .join(" · ")}
      </p>
    </main>
  );
}
