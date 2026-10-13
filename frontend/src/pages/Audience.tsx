import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import RankingRunner from "../components/RankingRunner";
import SimulationRunner from "../components/SimulationRunner";
import { getFamiliarity, listCreators } from "../services/creators";
import type { CreatorFamiliarity } from "../services/creators";
import type { Creator } from "../types/creator";

const env = import.meta.env as Record<string, string | undefined>;
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

export interface Viewer {
  id: number;
  handle: string;
  age_bracket: string;
  region: string;
  interests: string[];
  personality: string;
  humor_preferences: string[];
  attention_level: number;
  creator_affinities: Record<string, number>;
  response_style: string;
  audience_version: string;
  seed_index: number;
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return (await res.json()) as T;
}

export default function Audience() {
  const [viewers, setViewers] = useState<Viewer[] | null>(null);
  const [error, setError] = useState("");
  const [previewText, setPreviewText] = useState(
    "Hank's Old Red tractor breaks down the morning of an important delivery."
  );
  const [interests, setInterests] = useState<Record<number, number>>({});
  const [familiarity, setFamiliarity] = useState<CreatorFamiliarity | null>(null);

  const refresh = () =>
    req<Viewer[]>(`${ROOT}/api/audience`)
      .then(setViewers)
      .catch((e) => setError(e instanceof Error ? e.message : "load failed"));

  useEffect(() => {
    void refresh();
  }, []);

  // familiarity for the first creator (Sprint 11.2)
  useEffect(() => {
    listCreators()
      .then((cs: Creator[]) => {
        if (cs.length > 0) return getFamiliarity(cs[0].id);
        return null;
      })
      .then((f: CreatorFamiliarity | null) => setFamiliarity(f))
      .catch(() => setFamiliarity(null));
  }, []);

  const onSeed = async () => {
    try {
      await req<Viewer[]>(`${ROOT}/api/audience/seed`, {
        method: "POST",
        body: JSON.stringify({ count: 25 }),
      });
      await refresh();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "seed failed");
    }
  };

  const onPreview = async () => {
    if (!viewers) return;
    const next: Record<number, number> = {};
    for (const v of viewers) {
      const r = await req<{ interest: number }>(
        `${ROOT}/api/audience/${v.id}/preview`,
        {
          method: "POST",
          body: JSON.stringify({ text: previewText, tags: ["farming", "comedy"] }),
        }
      );
      next[v.id] = r.interest;
    }
    setInterests(next);
  };

  if (viewers === null)
    return <main style={{ padding: 24 }}>loading audience…</main>;

  const values = Object.values(interests);
  const spread =
    values.length > 0
      ? `spread: ${(Math.max(...values) - Math.min(...values)).toFixed(2)}`
      : "";

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 900 }}>
      <p>
        <Link to="/dashboard">← Dashboard</Link>
      </p>
      <h1>Synthetic audience (Sprint 4.1)</h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      {familiarity && (
        <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12 }}>
          <h2>Creator familiarity (Sprint 11.2)</h2>
          <p>
            {familiarity.creator_slug}: {familiarity.tiers.unknown} unknown ·{" "}
            {familiarity.tiers.familiar} familiar · {familiarity.tiers.favorite}{" "}
            favorite (of {familiarity.viewer_count})
          </p>
          <ul>
            {familiarity.viewers.slice(0, 5).map((v) => (
              <li key={v.viewer_id}>
                {v.handle}: {v.tier} (exposure {v.exposure.toFixed(2)})
              </li>
            ))}
          </ul>
        </div>
      )}

      {viewers.length === 0 ? (
        <div>
          <p>No viewers yet.</p>
          <button onClick={() => void onSeed()}>seed 25 viewers</button>
        </div>
      ) : (
        <>
          <p>
            {viewers.length} viewers · version {viewers[0].audience_version}
          </p>
          <h2>Identical-content check {spread}</h2>
          <textarea
            value={previewText}
            onChange={(e) => setPreviewText(e.target.value)}
            rows={2}
            style={{ width: "100%" }}
          />
          <br />
          <button onClick={() => void onPreview()}>run preview across all</button>
          <table>
            <thead>
              <tr>
                <th>viewer</th>
                <th>interests</th>
                <th>humor</th>
                <th>attention</th>
                <th>style</th>
                <th>interest</th>
              </tr>
            </thead>
            <tbody>
              {viewers.map((v) => (
                <tr key={v.id}>
                  <td>
                    {v.handle} ({v.personality}, {v.age_bracket})
                  </td>
                  <td>{v.interests.join(", ")}</td>
                  <td>{v.humor_preferences.join(", ")}</td>
                  <td>{v.attention_level}</td>
                  <td>{v.response_style}</td>
                  <td>
                    {interests[v.id] !== undefined ? interests[v.id].toFixed(2) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <SimulationRunner />
          <RankingRunner />
        </>
      )}
    </main>
  );
}
