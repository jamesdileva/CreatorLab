import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const env = import.meta.env as Record<string, string | undefined>;
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

interface QueueItem {
  id: number;
  title: string;
  episode_number: number;
  status: string;
  series_id: number;
  created_at: string;
}

interface Risk {
  code: string;
  severity: string;
  detail: string;
}

interface ReviewDetail {
  episode: {
    id: number;
    title: string;
    premise: string;
    synopsis: string;
    script: string;
    status: string;
    episode_number: number;
  };
  creator: { name: string } | null;
  series: { name: string } | null;
  scenes: { scene_number: number; title: string; direction: string }[];
  latest_render: {
    render_id: number;
    video_url: string;
    captions_url: string;
    manifest_url: string;
    total_duration: number;
    card_version: string;
  } | null;
  simulation: {
    run_id: number;
    aggregate: {
      viewer_count: number;
      means: Record<string, number>;
      reason_counts: Record<string, number>;
    };
  } | null;
  risks: Risk[];
  risk_status: string;
  metadata: { scene_count: number; word_count: number; status: string };
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return (await res.json()) as T;
}

export default function Review() {
  const [queue, setQueue] = useState<QueueItem[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [error, setError] = useState("");
  const [editScript, setEditScript] = useState("");
  const [saving, setSaving] = useState(false);

  const refreshQueue = () =>
    req<QueueItem[]>(`${ROOT}/api/review-queue`)
      .then(setQueue)
      .catch((e) => setError(e instanceof Error ? e.message : "load failed"));

  useEffect(() => {
    void refreshQueue();
  }, []);

  const openReview = (id: number) => {
    setSelectedId(id);
    req<ReviewDetail>(`${ROOT}/api/review-queue/${id}`)
      .then((d) => {
        setDetail(d);
        setEditScript(d.episode.script);
        setError("");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "load failed"));
  };

  const act = async (action: "approve" | "reject") => {
    if (!selectedId) return;
    try {
      await req(`${ROOT}/api/episodes/${selectedId}/${action}`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setDetail(null);
      setSelectedId(null);
      await refreshQueue();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : `${action} failed`);
    }
  };

  const saveEdit = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      await req(`${ROOT}/api/episodes/${selectedId}`, {
        method: "PATCH",
        body: JSON.stringify({ script: editScript }),
      });
      openReview(selectedId);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "save failed");
    } finally {
      setSaving(false);
    }
  };

  if (queue === null) return <main style={{ padding: 24 }}>loading queue…</main>;

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 1000 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link>
      </p>
      <h1>Approval queue (Sprint 6.1)</h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <div style={{ display: "flex", gap: 24 }}>
        <div style={{ minWidth: 260 }}>
          <h2>Pending ({queue.length})</h2>
          {queue.length === 0 ? (
            <p>queue empty</p>
          ) : (
            <ul>
              {queue.map((q) => (
                <li key={q.id}>
                  <button onClick={() => openReview(q.id)}>
                    Ep {q.episode_number}: {q.title} [{q.status}]
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div style={{ flex: 1 }}>
          {!detail ? (
            <p>select an episode to review</p>
          ) : (
            <>
              <h2>
                {detail.series?.name} — Ep {detail.episode.episode_number}:{" "}
                {detail.episode.title}
              </h2>
              <p>
                <strong>{detail.creator?.name}</strong> · {detail.episode.status} ·{" "}
                {detail.metadata.scene_count} scenes · {detail.metadata.word_count} words
              </p>

              <h3>Risks [{detail.risk_status}]</h3>
              <ul>
                {detail.risks.map((r, i) => (
                  <li
                    key={i}
                    style={{
                      color:
                        r.severity === "BLOCK"
                          ? "crimson"
                          : r.severity === "REVIEW"
                          ? "#a06000"
                          : "green",
                    }}
                  >
                    {r.severity}: {r.code} — {r.detail}
                  </li>
                ))}
              </ul>

              {detail.latest_render && (
                <>
                  <h3>Video ({detail.latest_render.total_duration.toFixed(1)}s)</h3>
                  <video
                    controls
                    src={`${ROOT}${detail.latest_render.video_url}`}
                    style={{ width: 270, height: 480, background: "#000" }}
                  />
                </>
              )}

              {detail.simulation && (
                <>
                  <h3>
                    Simulated audience ({detail.simulation.aggregate.viewer_count}{" "}
                    viewers)
                  </h3>
                  <ul>
                    {Object.entries(detail.simulation.aggregate.means).map(([k, v]) => (
                      <li key={k}>
                        {k.replace("_probability", "")}: {(v * 100).toFixed(1)}%
                      </li>
                    ))}
                  </ul>
                </>
              )}

              <h3>Script</h3>
              <textarea
                value={editScript}
                onChange={(e) => setEditScript(e.target.value)}
                rows={10}
                style={{ width: "100%" }}
              />
              <br />
              <button disabled={saving} onClick={() => void saveEdit()}>
                {saving ? "saving…" : "save edit"}
              </button>{" "}
              <button onClick={() => void act("approve")}>approve</button>{" "}
              <button onClick={() => void act("reject")}>reject</button>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
