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

export default function Analytics() {
  const [videos, setVideos] = useState<PublishedVideoSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${ROOT}/api/youtube/videos`)
      .then((r) => r.json())
      .then(setVideos)
      .catch(() => setVideos([]));
  }, []);

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
    </main>
  );
}
