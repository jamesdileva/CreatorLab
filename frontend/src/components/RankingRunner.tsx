import { useState } from "react";

const env = import.meta.env as Record<string, string | undefined>;
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

const METRICS = [
  "watch_probability",
  "like_probability",
  "comment_probability",
  "share_probability",
  "follow_probability",
];

export interface RankingResult {
  run: {
    id: number;
    candidate_type: string;
    candidate_ids: number[];
    metric: string;
    ranking: number[];
    audience_version: string;
    viewer_count: number;
  };
  ranked: { candidate_id: number; score: number; run_id: number }[];
}

export default function RankingRunner() {
  const [candidateType, setCandidateType] = useState("concept");
  const [ids, setIds] = useState("");
  const [metric, setMetric] = useState(METRICS[0]);
  const [result, setResult] = useState<RankingResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const onRank = async () => {
    const candidate_ids = ids
      .split(",")
      .map((s) => Number(s.trim()))
      .filter((n) => Number.isInteger(n) && n > 0);
    if (candidate_ids.length < 2) {
      setError("enter at least two candidate ids, comma-separated");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(`${ROOT}/api/simulations/rank`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_type: candidateType, candidate_ids, metric }),
      });
      if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
      setResult((await res.json()) as RankingResult);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "ranking failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginTop: 24 }}>
      <h2>Candidate ranking (Sprint 4.3)</h2>
      <p style={{ fontSize: 12, color: "#555" }}>
        Runs every candidate through the same {result?.run.viewer_count ?? 25}-viewer
        audience and orders them by the chosen metric.
      </p>
      <select value={candidateType} onChange={(e) => setCandidateType(e.target.value)}>
        <option value="concept">concept</option>
        <option value="episode">episode</option>
      </select>{" "}
      <input
        placeholder="candidate ids, e.g. 1,2,3,4"
        value={ids}
        onChange={(e) => setIds(e.target.value)}
        style={{ width: 180 }}
      />{" "}
      <select value={metric} onChange={(e) => setMetric(e.target.value)}>
        {METRICS.map((m) => (
          <option key={m} value={m}>
            {m.replace("_probability", "")}
          </option>
        ))}
      </select>{" "}
      <button disabled={busy} onClick={() => void onRank()}>
        {busy ? "ranking…" : "rank candidates"}
      </button>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {result && (
        <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12 }}>
          <p>
            ranking run {result.run.id} · {result.run.candidate_type}s by{" "}
            {result.run.metric}
          </p>
          <ol>
            {result.ranked.map((r) => (
              <li key={r.candidate_id}>
                #{r.candidate_id} — {(r.score * 100).toFixed(1)}%
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
