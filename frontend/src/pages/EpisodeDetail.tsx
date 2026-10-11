import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  archiveEpisode,
  createScene,
  deleteScene,
  getEpisode,
  listScenes,
  updateEpisode,
} from "../services/story";
import { EPISODE_STATUSES } from "../types/story";
import type { Episode, Scene } from "../types/story";

export default function EpisodeDetail() {
  const { id } = useParams<{ id: string }>();
  const episodeId = Number(id);
  const [episode, setEpisode] = useState<Episode | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [error, setError] = useState("");
  const [sceneTitle, setSceneTitle] = useState("");
  const [sceneDirection, setSceneDirection] = useState("");

  const refresh = () => {
    getEpisode(episodeId).then(setEpisode).catch((e) =>
      setError(e instanceof Error ? e.message : "load failed")
    );
    listScenes(episodeId).then(setScenes).catch(() => setScenes([]));
  };

  useEffect(refresh, [episodeId]);

  const onCreateScene = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createScene(episodeId, { title: sceneTitle, direction: sceneDirection });
      setSceneTitle("");
      setSceneDirection("");
      refresh();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "scene create failed");
    }
  };

  const onChangeStatus = async (status: string) => {
    try {
      setEpisode(await updateEpisode(episodeId, { status }));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "status change failed");
    }
  };

  const onArchive = async () => {
    try {
      setEpisode(await archiveEpisode(episodeId));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "archive failed");
    }
  };

  if (error && !episode) return <main style={{ padding: 24 }}>{error}</main>;
  if (!episode) return <main style={{ padding: 24 }}>loading…</main>;

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 760 }}>
      <p>
        <Link to={`/series/${episode.series_id}`}>← back to series</Link>
      </p>
      <h1>
        Episode {episode.episode_number}: {episode.title} [{episode.status}]
      </h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <p>
        <strong>Premise:</strong> {episode.premise || "—"}
      </p>
      <p>
        <strong>Synopsis:</strong> {episode.synopsis || "—"}
      </p>
      <pre style={{ background: "#f6f6f6", padding: 12, whiteSpace: "pre-wrap" }}>
        {episode.script || "(no script yet — script generation lands in later sprints)"}
      </pre>

      <label>
        status:{" "}
        <select
          value={episode.status}
          onChange={(e) => void onChangeStatus(e.target.value)}
        >
          {EPISODE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>{" "}
      {episode.status !== "ARCHIVED" && (
        <button onClick={() => void onArchive()}>archive</button>
      )}

      <h2>Scenes ({scenes.length})</h2>
      {scenes.length === 0 ? (
        <p>none yet</p>
      ) : (
        <ol>
          {scenes.map((s) => (
            <li key={s.id}>
              <strong>{s.title || `Scene ${s.scene_number}`}</strong>
              {s.direction && <> — {s.direction}</>}{" "}
              <button onClick={() => deleteScene(s.id).then(refresh).catch(() => undefined)}>
                delete
              </button>
            </li>
          ))}
        </ol>
      )}
      <form onSubmit={(e) => void onCreateScene(e)}>
        <input
          placeholder="scene title"
          value={sceneTitle}
          onChange={(e) => setSceneTitle(e.target.value)}
        />{" "}
        <input
          placeholder="direction"
          value={sceneDirection}
          onChange={(e) => setSceneDirection(e.target.value)}
          style={{ width: "50%" }}
        />{" "}
        <button type="submit">add scene</button>
      </form>
    </main>
  );
}
