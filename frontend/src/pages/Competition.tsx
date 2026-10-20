import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const env = import.meta.env as Record<string, string | undefined>;
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

interface Dimensions {
  growth: number | null;
  subscriber_conversion: number | null;
  retention: number | null;
  audience_loyalty: number | null;
  episode_performance: number | null;
}

interface Standing {
  creator_id: number;
  slug: string;
  name: string;
  videos_with_metrics: number;
  total_views: number;
  dimensions: Dimensions;
  ranks: Record<keyof Dimensions, number | null>;
  composite_rank: number | null;
  dimension_coverage: number;
  overall_rank: number | null;
  eligible: boolean;
}

interface Leaderboard {
  generated_at: string;
  min_episodes: number;
  interpretation_allowed: boolean;
  eligible_creators: number;
  leader: string | null;
  creators: Standing[];
  note: string;
}

const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);
const rank = (v: number | null) => (v === null ? "—" : `#${v}`);

export default function Competition() {
  const [data, setData] = useState<Leaderboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${ROOT}/api/competition/leaderboard`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setError("leaderboard failed"));
  }, []);

  if (error) return <main style={{ padding: 24 }}>{error}</main>;
  if (!data) return <main style={{ padding: 24 }}>loading…</main>;

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 1100 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link> ·{" "}
        <Link to="/analytics">Analytics</Link>
      </p>
      <h1>Creator competition</h1>
      <p>{data.note}</p>
      <p>
        {data.eligible_creators} eligible creator(s) · at least {data.min_episodes}{" "}
        published videos each · leader: {data.leader ?? "—"}
      </p>
      {!data.interpretation_allowed && (
        <p style={{ color: "#a06000" }}>
          Fewer than two creators have enough real-world episodes — standings are
          not interpretable yet (guide §15).
        </p>
      )}

      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>creator</th>
            <th>videos</th>
            <th>growth</th>
            <th>conversion</th>
            <th>retention</th>
            <th>loyalty</th>
            <th>mean views</th>
            <th>composite</th>
          </tr>
        </thead>
        <tbody>
          {data.creators.map((row) => (
            <tr key={row.creator_id} style={{ opacity: row.eligible ? 1 : 0.55 }}>
              <td>{row.overall_rank ?? "—"}</td>
              <td>
                <Link to={`/creators/${row.creator_id}`}>{row.name}</Link>
                {!row.eligible && " (not yet eligible)"}
              </td>
              <td>{row.videos_with_metrics}</td>
              <td>{row.dimensions.growth}</td>
              <td>{pct(row.dimensions.subscriber_conversion)}</td>
              <td>{pct(row.dimensions.retention)}</td>
              <td>{pct(row.dimensions.audience_loyalty)}</td>
              <td>{row.dimensions.episode_performance ?? "—"}</td>
              <td>
                {row.composite_rank ?? "—"}{" "}
                <span style={{ color: "#777" }}>
                  ({row.dimension_coverage}/5 dims)
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Per-dimension ranks</h3>
      <table>
        <thead>
          <tr>
            <th>creator</th>
            <th>growth</th>
            <th>conversion</th>
            <th>retention</th>
            <th>loyalty</th>
            <th>performance</th>
          </tr>
        </thead>
        <tbody>
          {data.creators
            .filter((row) => row.eligible)
            .map((row) => (
              <tr key={row.creator_id}>
                <td>{row.name}</td>
                <td>{rank(row.ranks.growth)}</td>
                <td>{rank(row.ranks.subscriber_conversion)}</td>
                <td>{rank(row.ranks.retention)}</td>
                <td>{rank(row.ranks.audience_loyalty)}</td>
                <td>{rank(row.ranks.episode_performance)}</td>
              </tr>
            ))}
        </tbody>
      </table>
      <p style={{ color: "#777" }}>
        Composite = mean rank across dimensions with data (lower is better).
        Generated {new Date(data.generated_at).toLocaleString()}.
      </p>
    </main>
  );
}
