import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const env = import.meta.env as Record<string, string | undefined>;
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

interface Bucket {
  comparisons: number;
  directional_accuracy: number | null;
  spearman: number | null;
  kendall_tau: number | null;
  top_1_hit_rate: number | null;
  disagreements: number;
  sample_sufficient: boolean;
}

interface Dashboard {
  generated_at: string;
  min_samples: number;
  experiments_scored: number;
  overall: Bucket;
  per_creator: Record<string, Bucket>;
  per_topic: Record<string, Bucket>;
  per_format: Record<string, Bucket>;
  interpretation_allowed: boolean;
}

const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);

function BucketTable({ title, data }: { title: string; data: Record<string, Bucket> }) {
  const rows = Object.entries(data);
  if (rows.length === 0) return null;
  return (
    <>
      <h3>{title}</h3>
      <table>
        <thead>
          <tr>
            <th>bucket</th>
            <th>comparisons</th>
            <th>directional</th>
            <th>spearman</th>
            <th>kendall τ</th>
            <th>top-1</th>
            <th>misses</th>
            <th>sufficient</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <td>{k}</td>
              <td>{v.comparisons}</td>
              <td>{pct(v.directional_accuracy)}</td>
              <td>{v.spearman ?? "—"}</td>
              <td>{v.kendall_tau ?? "—"}</td>
              <td>{pct(v.top_1_hit_rate)}</td>
              <td>{v.disagreements}</td>
              <td>{v.sample_sufficient ? "yes" : "no"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export default function RealityGapDashboard() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${ROOT}/api/experiments/reality-gap/dashboard`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setError("dashboard failed"));
  }, []);

  if (error) {
    return (
      <main style={{ padding: 24 }}>
        {error}
      </main>
    );
  }
  if (!data) return <main style={{ padding: 24 }}>loading…</main>;

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 900 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link> ·{" "}
        <Link to="/experiments">Experiments</Link>
      </p>
      <h1>Reality gap (Sprint 9.2)</h1>
      <p>
        {data.experiments_scored} scored experiments · minimum sample {data.min_samples}
      </p>
      {!data.interpretation_allowed && (
        <p style={{ color: "#a06000" }}>
          Not enough comparisons to interpret standings — collect more experiments
          (guide §15).
        </p>
      )}

      <BucketTable title="Overall" data={{ overall: data.overall }} />
      <BucketTable title="By creator" data={data.per_creator} />
      <BucketTable title="By topic" data={data.per_topic} />
      <BucketTable title="By format" data={data.per_format} />
    </main>
  );
}
