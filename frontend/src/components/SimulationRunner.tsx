import { useState } from "react";

const env = import.meta.env as Record<string, string | undefined>;
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

export interface SimAggregate {
  viewer_count: number;
  means: Record<string, number>;
  reason_counts: Record<string, number>;
  watch_buckets: Record<string, number>;
}

export interface SimRun {
  run: {
    id: number;
    run_uuid: string;
    target_type: string;
    target_id: number;
    model: string;
    prompt_version: string;
    audience_version: string;
    viewer_count: number;
  };
  aggregate: SimAggregate;
}

export default function SimulationRunner() {
  const [targetType, setTargetType] = useState("concept");
  const [targetId, setTargetId] = useState("");
  const [result, setResult] = useState<SimRun | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const onRun = async () => {
    setBusy(true);
    try {
      const res = await fetch(`${ROOT}/api/simulations/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_type: targetType, target_id: Number(targetId) }),
      });
      if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
      setResult((await res.json()) as SimRun);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "run failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginTop: 24 }}>
      <h2>Run simulation (Sprint 4.2)</h2>
      <select value={targetType} onChange={(e) => setTargetType(e.target.value)}>
        <option value="concept">concept</option>
        <option value="episode">episode</option>
      </select>{" "}
      <input
        placeholder="target id"
        value={targetId}
        onChange={(e) => setTargetId(e.target.value)}
        style={{ width: 90 }}
      />{" "}
      <button disabled={busy || !targetId} onClick={() => void onRun()}>
        {busy ? "simulating…" : "simulate"}
      </button>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {result && (
        <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12 }}>
          <p>
            run {result.run.id} · {result.run.target_type} #{result.run.target_id} ·{" "}
            {result.aggregate.viewer_count} viewers · model {result.run.model} ·{" "}
            prompt {result.run.prompt_version}
          </p>
          <ul>
            {Object.entries(result.aggregate.means).map(([k, v]) => (
              <li key={k}>
                {k.replace("_probability", "")}: {(v * 100).toFixed(1)}%
              </li>
            ))}
          </ul>
          <p style={{ fontSize: 12 }}>
            reasons:{" "}
            {Object.entries(result.aggregate.reason_counts)
              .map(([k, v]) => `${k}×${v}`)
              .join(", ")}
          </p>
          <p style={{ fontSize: 12 }}>
            watch buckets:{" "}
            {Object.entries(result.aggregate.watch_buckets)
              .map(([k, v]) => `${k}=${v}`)
              .join(", ")}
          </p>
        </div>
      )}
    </div>
  );
}
