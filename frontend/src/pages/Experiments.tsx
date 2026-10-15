import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

const env = import.meta.env as Record<string, string | undefined>;
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

interface ExperimentRow {
  id: number;
  episode_id: number;
  hypothesis: string;
  variant: string;
  simulation_score: number | null;
  simulation_rank: number | null;
  conclusions: string;
}

interface Lifecycle {
  experiment: {
    id: number;
    hypothesis: string;
    variant: string;
    simulation_score: number | null;
    simulation_rank: number | null;
    reality_gap: unknown;
    conclusions: string;
  };
  creator: { name: string } | null;
  series: { name: string } | null;
  episode: { id: number; title: string; episode_number: number; status: string } | null;
  simulation: {
    run_id: number;
    model: string;
    aggregate: {
      viewer_count: number;
      means: Record<string, number>;
    } | null;
  } | null;
  render: { id: number; status: string; total_duration: number } | null;
  published_video: {
    video_id: string;
    status: string;
    privacy_status: string;
    upload_time: string;
  } | null;
  metrics: {
    id: number;
    captured_at: string;
    views: number;
    likes: number;
    comments: number;
    subscriber_count: number;
  }[];
}

interface RealityGap {
  sim_order: number[];
  real_order: number[];
  sample_size: number;
  correlation: { spearman: number | null; kendall_tau: number | null };
  agreement: { top_1_match: boolean | null; top_k_overlap: number | null; directional_accuracy: number | null };
  disagreements: { sim_order: string; real_order: string }[];
  rank_deltas: Record<string, number>;
}

interface GapBucket {
  comparisons: number;
  directional_accuracy: number | null;
  spearman: number | null;
  kendall_tau: number | null;
  top_1_hit_rate: number | null;
  disagreements: number;
  sample_sufficient: boolean;
}

interface Calibration {
  min_samples: number;
  samples: number;
  interpretation_allowed: boolean;
  model: { slope: number; intercept: number; residual_std: number; form: string };
  coverage: number | null;
  mae: number | null;
  mape: number | null;
  predictions: {
    experiment_id: number;
    simulator_score: number;
    observed_views: number;
    predicted: { point: number; low: number; high: number };
    within_range: boolean;
  }[];
  verdict: string;
}

interface GapDashboard {
  generated_at: string;
  min_samples: number;
  experiments_scored: number;
  overall: GapBucket;
  per_creator: Record<string, GapBucket>;
  per_topic: Record<string, GapBucket>;
  per_format: Record<string, GapBucket>;
  interpretation_allowed: boolean;
}

interface Checkpoint {
  generated_at: string;
  min_samples: number;
  experiments_scored: number;
  simulator: {
    comparisons: number;
    directional_accuracy: number | null;
    top_1_hit_rate: number | null;
  };
  random_baseline: { directional_accuracy: number; top_1_hit_rate: number | null };
  random_selector?: { trials: number; directional_accuracy: number | null; top_1_hit_rate: number | null };
  deltas: { directional: number | null; top_1: number | null };
  human_baseline: unknown;
  human_note: string;
  verdict: string;
  verdict_text?: string;
  interpretation_allowed: boolean;
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return (await res.json()) as T;
}

export default function Experiments() {
  const [rows, setRows] = useState<ExperimentRow[]>([]);
  const [episodeId, setEpisodeId] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [error, setError] = useState("");
  const [dashboard, setDashboard] = useState<GapDashboard | null>(null);
  const [checkpoint, setCheckpoint] = useState<Checkpoint | null>(null);
  const [calibration, setCalibration] = useState<Calibration | null>(null);

  useEffect(() => {
    req<ExperimentRow[]>(`${ROOT}/api/experiments`)
      .then(setRows)
      .catch(() => setRows([]));
    req<GapDashboard>(`${ROOT}/api/experiments/reality-gap/dashboard`)
      .then(setDashboard)
      .catch(() => setDashboard(null));
    req<Checkpoint>(`${ROOT}/api/experiments/research-checkpoint`)
      .then(setCheckpoint)
      .catch(() => setCheckpoint(null));
    req<Calibration>(`${ROOT}/api/experiments/calibration`)
      .then(setCalibration)
      .catch(() => setCalibration(null));
  }, []);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await req(`${ROOT}/api/experiments`, {
        method: "POST",
        body: JSON.stringify({ episode_id: Number(episodeId), hypothesis }),
      });
      setEpisodeId("");
      setHypothesis("");
      req<ExperimentRow[]>(`${ROOT}/api/experiments`).then(setRows);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "create failed");
    }
  };

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 800 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link>
      </p>
      <h1>Experiments (Sprint 8.2)</h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <h2>First research checkpoint (Sprint 9.3)</h2>
      {checkpoint ? (
        <div style={{ border: "1px solid #999", borderRadius: 8, padding: 12 }}>
          <p>
            <strong>verdict: {checkpoint.verdict}</strong> ·{" "}
            {checkpoint.experiments_scored} scored · sim directional{" "}
            {checkpoint.simulator.directional_accuracy ?? "—"} vs random{" "}
            {checkpoint.random_baseline.directional_accuracy} (Δ{" "}
            {checkpoint.deltas.directional ?? "—"}) · top-1{" "}
            {checkpoint.simulator.top_1_hit_rate ?? "—"} vs random{" "}
            {checkpoint.random_baseline.top_1_hit_rate ?? "—"}
          </p>
          {checkpoint.verdict_text && <p>{checkpoint.verdict_text}</p>}
          {checkpoint.random_selector && checkpoint.random_selector.trials > 0 && (
            <p>
              shuffled-selector baseline ({checkpoint.random_selector.trials} seeded
              trials): directional {checkpoint.random_selector.directional_accuracy} ·
              top-1 {checkpoint.random_selector.top_1_hit_rate}
            </p>
          )}
          {!checkpoint.interpretation_allowed && (
            <p>Not enough comparisons yet (need ≥{checkpoint.min_samples}) — no interpretation.</p>
          )}
          <p>human baseline: {checkpoint.human_note}</p>
        </div>
      ) : (
        <p>checkpoint unavailable</p>
      )}
      <h2>Reality-gap dashboard (Sprint 9.2)</h2>
      {dashboard ? (
        <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12 }}>
          <p>
            {dashboard.experiments_scored} scored · overall directional{" "}
            {dashboard.overall.directional_accuracy ?? "—"} · top-1{" "}
            {dashboard.overall.top_1_hit_rate ?? "—"} · spearman{" "}
            {dashboard.overall.spearman ?? "—"} · disagreements{" "}
            {dashboard.overall.disagreements} (n=
            {dashboard.overall.comparisons}
            {dashboard.overall.sample_sufficient ? ", sufficient" : ", need ≥" + dashboard.min_samples})
          </p>
          {!dashboard.interpretation_allowed && (
            <p>Not enough experiments yet — numbers carry sample counts, no interpretation.</p>
          )}
          {(["per_creator", "per_topic", "per_format"] as const).map((section) => (
            <div key={section}>
              <h3>{section}</h3>
              <ul>
                {Object.entries(dashboard[section]).map(([k, v]) => (
                  <li key={k}>
                    {k}: dir {v.directional_accuracy ?? "—"} · top-1{" "}
                    {v.top_1_hit_rate ?? "—"} · n={v.comparisons}
                    {v.sample_sufficient ? "" : " (insufficient)"} · misses{" "}
                    {v.disagreements}
                  </li>
                ))}
                {Object.keys(dashboard[section]).length === 0 && <li>—</li>}
              </ul>
            </div>
          ))}
        </div>
      ) : (
        <p>dashboard unavailable</p>
      )}

      <h2>Calibration (Sprint 15.1)</h2>
      {calibration ? (
        <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12 }}>
          <p>
            samples {calibration.samples} (need ≥{calibration.min_samples}) ·{" "}
            {calibration.model.form} = {calibration.model.slope}·score +{" "}
            {calibration.model.intercept} · residual σ {calibration.model.residual_std}
          </p>
          {calibration.interpretation_allowed ? (
            <p>
              range coverage {(calibration.coverage! * 100).toFixed(1)}% · MAE{" "}
              {calibration.mae} · MAPE{" "}
              {calibration.mape !== null
                ? `${(calibration.mape * 100).toFixed(1)}%`
                : "—"}{" "}
              — {calibration.verdict}
            </p>
          ) : (
            <p>Insufficient samples — ranges withheld until ≥{calibration.min_samples}.</p>
          )}
          {calibration.predictions.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>experiment</th>
                  <th>score</th>
                  <th>observed</th>
                  <th>predicted range</th>
                  <th>in range</th>
                </tr>
              </thead>
              <tbody>
                {calibration.predictions.map((p) => (
                  <tr key={p.experiment_id}>
                    <td>#{p.experiment_id}</td>
                    <td>{p.simulator_score}</td>
                    <td>{p.observed_views}</td>
                    <td>
                      {p.predicted.low}–{p.predicted.high} (point{" "}
                      {p.predicted.point})
                    </td>
                    <td>{p.within_range ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <p>calibration unavailable</p>
      )}
      <ul>
        {rows.map((r) => (
          <li key={r.id}>
            <Link to={`/experiments/${r.id}`}>
              EXPERIMENT-{String(r.id).padStart(4, "0")}
            </Link>{" "}
            ep {r.episode_id} · score {r.simulation_score ?? "—"} · rank{" "}
            {r.simulation_rank ?? "—"} · {r.hypothesis || "(no hypothesis)"}
          </li>
        ))}
        {rows.length === 0 && <li>none yet</li>}
      </ul>
      <h2>Bind experiment</h2>
      <form onSubmit={(e) => void onCreate(e)}>
        <input
          placeholder="episode id"
          value={episodeId}
          onChange={(e) => setEpisodeId(e.target.value)}
          style={{ width: 110 }}
        />{" "}
        <input
          placeholder="hypothesis"
          value={hypothesis}
          onChange={(e) => setHypothesis(e.target.value)}
          style={{ width: "55%" }}
        />{" "}
        <button type="submit">bind</button>
      </form>
    </main>
  );
}

export function ExperimentDetail() {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<Lifecycle | null>(null);
  const [gap, setGap] = useState<RealityGap | null>(null);
  const [gapError, setGapError] = useState("");
  const [conclusions, setConclusions] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    req<Lifecycle>(`${ROOT}/api/experiments/${id}`)
      .then((d) => {
        setDetail(d);
        setConclusions(d.experiment.conclusions);
        if (d.experiment.reality_gap) setGap(d.experiment.reality_gap as RealityGap);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "load failed"));
  }, [id]);

  const onComputeGap = async () => {
    if (!id) return;
    setGapError("");
    try {
      const res = await req<RealityGap>(`${ROOT}/api/experiments/${id}/reality-gap`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setGap(res);
      setDetail((d) => (d ? { ...d, experiment: { ...d.experiment, reality_gap: res } } : d));
    } catch (err) {
      setGapError(err instanceof Error ? err.message : "reality gap failed");
    }
  };

  const onSave = async () => {
    if (!id) return;
    try {
      await req(`${ROOT}/api/experiments/${id}/conclusions`, {
        method: "PATCH",
        body: JSON.stringify({ conclusions }),
      });
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "save failed");
    }
  };

  if (!detail) return <main style={{ padding: 24 }}>{error || "loading…"}</main>;

  const step = (label: string, value: string | null) => (
    <li>
      <strong>{label}:</strong> {value ?? "—"}
    </li>
  );

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 800 }}>
      <p>
        <Link to="/experiments">← Experiments</Link>
      </p>
      <h1>
        EXPERIMENT-{detail.experiment.id.toString().padStart(4, "0")} lifecycle
      </h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <ol>
        {step(
          "Creator/series",
          `${detail.creator?.name ?? "?"} / ${detail.series?.name ?? "?"}`
        )}
        {step(
          "Episode",
          detail.episode
            ? `Ep ${detail.episode.episode_number}: ${detail.episode.title} [${detail.episode.status}]`
            : null
        )}
        {step("Hypothesis", detail.experiment.hypothesis || "(none)")}
        {step(
          "Simulation",
          detail.simulation
            ? `run ${detail.simulation.run_id} · watch ${
                detail.simulation.aggregate
                  ? (detail.simulation.aggregate.means.watch_probability * 100).toFixed(1)
                  : "?"
              }% · rank ${detail.experiment.simulation_rank ?? "?"} (${
                detail.simulation.model
              })`
            : null
        )}
        {step(
          "Render",
          detail.render
            ? `#${detail.render.id} [${detail.render.status}] ${detail.render.total_duration.toFixed(1)}s`
            : null
        )}
        {step(
          "Published video",
          detail.published_video
            ? `${detail.published_video.video_id} [${detail.published_video.status}/${detail.published_video.privacy_status}]`
            : null
        )}
        <li>
          <strong>Analytics snapshots ({detail.metrics.length}):</strong>{" "}
          {detail.metrics.map((m) => `${m.views}v@${m.captured_at.split("T")[0]}`).join(", ") ||
            "—"}
        </li>
        {step(
          "Reality gap",
          detail.experiment.reality_gap
            ? "computed below"
            : "(Sprint 9.1)"
        )}
      </ol>

      <h2>Reality gap (Sprint 9.1)</h2>
      {gapError && <p style={{ color: "crimson" }}>{gapError}</p>}
      <button onClick={() => void onComputeGap()}>compute reality gap</button>
      {gap && (
        <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12 }}>
          <p>
            simulated: {gap.sim_order.join(" > ")} · real:{" "}
            {gap.real_order.join(" > ")}
          </p>
          {gap.sample_size >= 2 ? (
            <p>
              spearman {gap.correlation.spearman} · kendall τ{" "}
              {gap.correlation.kendall_tau} · directional{" "}
              {gap.agreement.directional_accuracy} · top-1{" "}
              {String(gap.agreement.top_1_match)} (n={gap.sample_size})
            </p>
          ) : (
            <p>needs at least 2 published episodes to correlate (n={gap.sample_size})</p>
          )}
          {gap.disagreements.length > 0 ? (
            <>
              <p>
                <strong>{gap.disagreements.length} disagreement(s)</strong>
              </p>
              <ul>
                {gap.disagreements.map((d, i) => (
                  <li key={i}>
                    sim {d.sim_order} vs real {d.real_order}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            gap.sample_size >= 2 && <p>simulator and reality agree on all pairs</p>
          )}
        </div>
      )}
      <h2>Conclusions</h2>
      <textarea
        value={conclusions}
        onChange={(e) => setConclusions(e.target.value)}
        rows={4}
        style={{ width: "100%" }}
      />
      <br />
      <button onClick={() => void onSave()}>save conclusions</button>
    </main>
  );
}
