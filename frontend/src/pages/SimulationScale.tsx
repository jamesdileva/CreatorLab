import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const env = import.meta.env as Record<string, string | undefined>;
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

interface SizeResult {
  viewer_count: number;
  episodes: number;
  comparisons: number;
  directional_accuracy: number | null;
  spearman: number | null;
  kendall_tau: number | null;
  top_1_match: boolean;
  mean_sim_score: number;
  useful: boolean;
}

interface Study {
  study_id: number;
  run_uuid: string;
  metric: string;
  sizes: number[];
  episode_ids: number[];
  min_pairs: number;
  threshold: number;
  interpretation_allowed: boolean;
  min_useful_viewer_count: number | null;
  results: SizeResult[];
  note: string;
  created_at: string | null;
}

const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);

export default function SimulationScale() {
  const [studies, setStudies] = useState<Study[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    fetch(`${ROOT}/api/simulation-scale/studies`)
      .then((r) => r.json())
      .then(setStudies)
      .catch(() => setError("could not load scale studies"));

  useEffect(() => {
    void load();
  }, []);

  const runStudy = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`${ROOT}/api/simulation-scale/studies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(await res.text());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "study failed");
    } finally {
      setBusy(false);
    }
  };

  if (!studies) return <main style={{ padding: 24 }}>loading scale studies…</main>;
  const latest = studies[0] ?? null;

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 1000 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link> ·{" "}
        <Link to="/simulation">Synthetic audience</Link>
      </p>
      <h1>Large-scale simulation</h1>
      <p style={{ maxWidth: 720 }}>
        Simulates the same real-world episodes at 25 → 100 → 500 → 1,000 →
        10,000 viewers, then ranks them against actual views. Larger populations
        are not assumed to be better; the ladder measures directional accuracy at
        each size.
      </p>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <button onClick={() => void runStudy()} disabled={busy}>
        {busy ? "running ladder…" : "run 25 → 10,000 ladder"}
      </button>
      <p style={{ color: "#777" }}>
        Needs at least two published episodes with real view metrics. The 10,000
        viewer run can take a while.
      </p>

      {latest ? (
        <section>
          <h2>Latest study #{latest.study_id}</h2>
          <p>
            {latest.episode_ids.length} episodes · metric {latest.metric} ·
            minimum useful size:{" "}
            <strong>{latest.min_useful_viewer_count ?? "not reached"}</strong>
          </p>
          <p style={{ color: "#777" }}>{latest.note}</p>
          <table>
            <thead>
              <tr>
                <th>viewers</th>
                <th>pairs</th>
                <th>directional</th>
                <th>spearman</th>
                <th>kendall τ</th>
                <th>top-1</th>
                <th>mean sim</th>
                <th>useful</th>
              </tr>
            </thead>
            <tbody>
              {latest.results.map((row) => (
                <tr key={row.viewer_count}>
                  <td>{row.viewer_count.toLocaleString()}</td>
                  <td>{row.comparisons}</td>
                  <td>{pct(row.directional_accuracy)}</td>
                  <td>{row.spearman ?? "—"}</td>
                  <td>{row.kendall_tau ?? "—"}</td>
                  <td>{row.top_1_match ? "yes" : "no"}</td>
                  <td>{row.mean_sim_score}</td>
                  <td>{row.useful ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : (
        <p>No scale studies yet.</p>
      )}

      {studies.length > 1 && (
        <>
          <h2>Earlier studies</h2>
          <ul>
            {studies.slice(1).map((study) => (
              <li key={study.study_id}>
                #{study.study_id} · {study.sizes.join(", ")} viewers · min useful{" "}
                {study.min_useful_viewer_count ?? "not reached"}
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
