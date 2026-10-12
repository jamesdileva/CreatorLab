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

  useEffect(() => {
    req<ExperimentRow[]>(`${ROOT}/api/experiments`)
      .then(setRows)
      .catch(() => setRows([]));
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
  const [error, setError] = useState("");
  const [conclusions, setConclusions] = useState("");

  useEffect(() => {
    if (!id) return;
    req<Lifecycle>(`${ROOT}/api/experiments/${id}`)
      .then((d) => {
        setDetail(d);
        setConclusions(d.experiment.conclusions);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "load failed"));
  }, [id]);

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
            ? JSON.stringify(detail.experiment.reality_gap)
            : "(Sprint 9.1)"
        )}
      </ol>
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
