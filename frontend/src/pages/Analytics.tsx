import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const env = import.meta.env as Record<string, string | undefined>;
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

interface PublishedVideoSummary {
  id: number;
  episode_id: number;
  video_id: string;
  title: string;
  status: string;
  privacy_status: string;
  upload_time: string;
}

interface Snapshot {
  id: number;
  video_id: string;
  captured_at: string;
  views: number;
  likes: number;
  comments: number;
  subscriber_count: number;
  subscribers_gained: number;
}

interface Forecast {
  min_samples: number;
  samples: number;
  interpretation_allowed: boolean;
  model: { factor: number; factor_std: number; form: string };
  coverage: number | null;
  mae: number | null;
  mape: number | null;
  forecasts: {
    published_video_id: number;
    early_hours: number;
    early_views: number;
    actual_24h_views: number;
    predicted: { point: number; low: number; high: number };
    within_range: boolean;
  }[];
  verdict: string;
  prediction_for_early_views?: {
    early_views: number;
    point: number;
    low: number;
    high: number;
  };
}

export default function Analytics() {
  const [videos, setVideos] = useState<PublishedVideoSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [earlyViews, setEarlyViews] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${ROOT}/api/youtube/videos`)
      .then((r) => r.json())
      .then(setVideos)
      .catch(() => setVideos([]));
    fetch(`${ROOT}/api/youtube/analytics/forecast`)
      .then((r) => r.json())
      .then(setForecast)
      .catch(() => setForecast(null));
  }, []);

  const predictFromEarly = async () => {
    try {
      const res = await fetch(
        `${ROOT}/api/youtube/analytics/forecast?early_views=${encodeURIComponent(earlyViews)}`
      );
      if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
      setForecast(await res.json());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "forecast failed");
    }
  };

  const openHistory = (id: number) => {
    setSelected(id);
    fetch(`${ROOT}/api/youtube/published/${id}/metrics`)
      .then((r) => r.json())
      .then(setHistory)
      .catch(() => setHistory([]));
  };

  const onSnapshot = async (id: number) => {
    try {
      const res = await fetch(`${ROOT}/api/youtube/published/${id}/snapshot`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
      setError("");
      openHistory(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "snapshot failed");
    }
  };

  const latest = history[history.length - 1];
  const first = history[0];

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 900 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link>
      </p>
      <h1>Analytics (Sprint 8.1)</h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <h2>Published videos ({videos.length})</h2>
      {videos.length === 0 ? (
        <p>none published yet</p>
      ) : (
        <ul>
          {videos.map((v) => (
            <li key={v.id}>
              <button onClick={() => openHistory(v.id)}>
                {v.title || v.video_id}
              </button>{" "}
              [{v.status}]{" "}
              <button onClick={() => void onSnapshot(v.id)}>snapshot now</button>
            </li>
          ))}
        </ul>
      )}

      {selected !== null && (
        <>
          <h2>
            History{" "}
            {history.length > 0 &&
              latest &&
              first &&
              `(views ${first.views} → ${latest.views}, subs +${history.reduce(
                (n, h) => n + h.subscribers_gained,
                0
              )})`}
          </h2>
          {history.length === 0 ? (
            <p>no snapshots yet</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>captured</th>
                  <th>views</th>
                  <th>likes</th>
                  <th>comments</th>
                  <th>subs</th>
                  <th>subs gained</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id}>
                    <td>{h.captured_at}</td>
                    <td>{h.views}</td>
                    <td>{h.likes}</td>
                    <td>{h.comments}</td>
                    <td>{h.subscriber_count}</td>
                    <td>+{h.subscribers_gained}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      <h2>Early performance forecast — 1h → 24h (Sprint 15.2)</h2>
      {forecast ? (
        <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12 }}>
          <p>
            samples {forecast.samples} (need ≥{forecast.min_samples}) ·{" "}
            {forecast.model.form.replace("factor", forecast.model.factor.toString())}{" "}
            · factor σ {forecast.model.factor_std}
          </p>
          {forecast.interpretation_allowed ? (
            <p>
              range coverage {(forecast.coverage! * 100).toFixed(1)}% · MAE{" "}
              {forecast.mae} · MAPE{" "}
              {forecast.mape !== null
                ? `${(forecast.mape * 100).toFixed(1)}%`
                : "—"}{" "}
              — {forecast.verdict}
            </p>
          ) : (
            <p>Insufficient videos with both a ~1h and a ≥24h reading.</p>
          )}
          <p>
            predict from first hour:{" "}
            <input
              value={earlyViews}
              onChange={(e) => setEarlyViews(e.target.value)}
              placeholder="views at 1h"
              style={{ width: 100 }}
            />{" "}
            <button onClick={() => void predictFromEarly()}>forecast 24h</button>
            {forecast.prediction_for_early_views && (
              <span>
                {" "}
                → {forecast.prediction_for_early_views.low}–
                {forecast.prediction_for_early_views.high} views (point{" "}
                {forecast.prediction_for_early_views.point})
              </span>
            )}
          </p>
          {forecast.forecasts.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>video</th>
                  <th>1h views</th>
                  <th>actual 24h</th>
                  <th>predicted range</th>
                  <th>in range</th>
                </tr>
              </thead>
              <tbody>
                {forecast.forecasts.map((f) => (
                  <tr key={f.published_video_id}>
                    <td>#{f.published_video_id}</td>
                    <td>{f.early_views}</td>
                    <td>{f.actual_24h_views}</td>
                    <td>
                      {f.predicted.low}–{f.predicted.high} (point{" "}
                      {f.predicted.point})
                    </td>
                    <td>{f.within_range ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <p>forecast unavailable</p>
      )}
    </main>
  );
}
