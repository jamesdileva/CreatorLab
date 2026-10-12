import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { listPublishedVideos } from "../services/story";
import type { PublishedVideoRecord } from "../services/story";

const env = import.meta.env as Record<string, string | undefined>;
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

interface Account {
  id: number;
  channel_id: string;
  channel_name: string;
  status: string;
  scopes: string;
  last_sync: string | null;
}

async function req<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return (await res.json()) as T;
}

export default function YouTube() {
  const [params] = useSearchParams();
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [videos, setVideos] = useState<PublishedVideoRecord[]>([]);
  const [error, setError] = useState("");

  const refresh = () => {
    req<{ configured: boolean }>(`${ROOT}/api/youtube/status`)
      .then((s) => setConfigured(s.configured))
      .catch(() => setConfigured(null));
    req<Account[]>(`${ROOT}/api/youtube/accounts`)
      .then(setAccounts)
      .catch(() => setAccounts([]));
    listPublishedVideos()
      .then(setVideos)
      .catch(() => setVideos([]));
  };

  useEffect(refresh, []);

  const onConnect = async () => {
    try {
      const res = await fetch(`${ROOT}/api/youtube/oauth/start`);
      if (!res.ok) throw new Error(`API ${res.status}`);
      const { authorize_url } = (await res.json()) as { authorize_url: string };
      window.location.href = authorize_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not start OAuth");
    }
  };

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 720 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link>
      </p>
      <h1>YouTube (Sprint 7.1)</h1>
      {params.get("error") && (
        <p style={{ color: "crimson" }}>connect failed: {params.get("error")}</p>
      )}
      {params.get("connected") && (
        <p style={{ color: "green" }}>connected channel: {params.get("connected")}</p>
      )}
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <p>
        OAuth credentials:{" "}
        {configured === null
          ? "unknown"
          : configured
          ? "configured (.env)"
          : "not configured — add YOUTUBE_CLIENT_ID/SECRET to .env"}
      </p>

      <button
        disabled={configured === false}
        onClick={() => void onConnect()}
      >
        connect a YouTube channel
      </button>

      <h2>Authorized channels</h2>
      {accounts.length === 0 ? (
        <p>none connected</p>
      ) : (
        <ul>
          {accounts.map((a) => (
            <li key={a.id}>
              <strong>{a.channel_name || a.channel_id}</strong> ({a.status}) · id{" "}
              {a.channel_id}
              {a.last_sync && <> · synced {a.last_sync}</>}
            </li>
          ))}
        </ul>
      )}
      <p style={{ fontSize: 12, color: "#555" }}>
        Tokens are stored outside version control (secrets/); the database keeps
        only a reference. Publish stays human-approved (Sprint 7.2+).
      </p>

      <h2>Published videos (Sprint 7.2)</h2>
      {videos.length === 0 ? (
        <p>none published yet</p>
      ) : (
        <ul>
          {videos.map((v) => (
            <li key={v.id}>
              <strong>{v.title || v.video_id}</strong> [{v.privacy_status}] —{" "}
              {v.status} · ep {v.episode_id} · {(v.total_duration || 0).toFixed(1)}s ·{" "}
              {v.upload_time}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
