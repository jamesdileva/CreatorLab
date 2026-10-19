import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { publishEpisode } from "../services/story";

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

interface RiskRow {
  episode_id: number;
  title: string;
  episode_number: number;
  status: string;
  series_id: number;
  level: string;
  fast_lane: boolean;
  reasons: string[];
  classifier_version: string;
}

const LEVEL_COLOR: Record<string, string> = {
  HIGH: "crimson",
  MEDIUM: "#a06000",
  LOW: "green",
};

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
  const [publishing, setPublishing] = useState(false);
  const [publishedMsg, setPublishedMsg] = useState("");
  const [risk, setRisk] = useState<Record<number, RiskRow>>({});
  const [fastBusy, setFastBusy] = useState(false);
  const [fastMsg, setFastMsg] = useState("");

  const refreshQueue = () =>
    req<QueueItem[]>(`${ROOT}/api/review-queue`)
      .then(setQueue)
      .catch((e) => setError(e instanceof Error ? e.message : "load failed"));

  const refreshRisk = () =>
    req<RiskRow[]>(`${ROOT}/api/review-queue/risk`)
      .then((rows) =>
        setRisk(Object.fromEntries(rows.map((r) => [r.episode_id, r])))
      )
      .catch(() => setRisk({}));

  useEffect(() => {
    void refreshQueue();
    void refreshRisk();
  }, []);

  const runFastLane = async () => {
    setFastBusy(true);
    try {
      const out = await req<{
        approved: number[];
        skipped: number[];
        classifier_version: string;
      }>(`${ROOT}/api/review-queue/fast-lane`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setFastMsg(
        `fast lane approved ${out.approved.length}, skipped ${out.skipped.length} (${out.classifier_version})`
      );
      await refreshQueue();
      await refreshRisk();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "fast lane failed");
    } finally {
      setFastBusy(false);
    }
  };

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

  const act = async (action: "approve" | "reject" | "fast-approve") => {
    if (!selectedId) return;
    try {
      await req(`${ROOT}/api/episodes/${selectedId}/${action}`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setDetail(null);
      setSelectedId(null);
      await refreshQueue();
      await refreshRisk();
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

  const onPublish = async () => {
    if (!selectedId) return;
    setPublishing(true);
    try {
      const res = await publishEpisode(selectedId);
      setPublishedMsg(`private upload recorded: video ${res.video_id}`);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "publish failed");
    } finally {
      setPublishing(false);
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

      <h2>Risk-based approval (Sprint 21.2)</h2>
      <p style={{ fontSize: 12, color: "#555" }}>
        LOW-risk items may take a faster path — still an explicit, human action.
        MEDIUM/HIGH require standard review; publishing stays a separate step.
      </p>
      <button disabled={fastBusy || !queue || queue.length === 0} onClick={() => void runFastLane()}>
        {fastBusy ? "approving…" : "fast-lane approve LOW-risk"}
      </button>
      {fastMsg && <p style={{ color: "green" }}>{fastMsg}</p>}

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
                    Ep {q.episode_number}: {q.title} [{q.status}]{" "}
                    {risk[q.id] && (
                      <span style={{ color: LEVEL_COLOR[risk[q.id].level] }}>
                        [{risk[q.id].level}
                        {risk[q.id].fast_lane ? "·fast" : ""}]
                      </span>
                    )}
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
              {selectedId != null && risk[selectedId] && (
                <p style={{ color: LEVEL_COLOR[risk[selectedId].level] }}>
                  <strong>risk level: {risk[selectedId].level}</strong>
                  {risk[selectedId].fast_lane
                    ? " — eligible for fast lane"
                    : " — standard review required"}
                </p>
              )}
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
              {selectedId != null && risk[selectedId]?.fast_lane && (
                <button onClick={() => void act("fast-approve")}>
                  fast-approve (LOW)
                </button>
              )}{" "}
              <button onClick={() => void act("reject")}>reject</button>{" "}
              <button disabled={publishing} onClick={() => void onPublish()}>
                {publishing ? "publishing…" : "publish privately"}
              </button>
              {publishedMsg && <p style={{ color: "green" }}>{publishedMsg}</p>}
            </>
          )}
        </div>
      </div>
    </main>
  );
}
