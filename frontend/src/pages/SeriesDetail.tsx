import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  createCanon,
  createEpisode,
  createThread,
  endSeries,
  listCanon,
  listEpisodeHistory,
  listThreads,
  resolveThread,
} from "../services/story";
import { CANON_CATEGORIES } from "../types/story";
import type { CanonEntry, Episode, StoryThread } from "../types/story";
import { getSeries } from "../services/story";
import type { Series } from "../types/story";

export default function SeriesDetail() {
  const { id } = useParams<{ id: string }>();
  const seriesId = Number(id);
  const [series, setSeries] = useState<Series | null>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [threads, setThreads] = useState<StoryThread[]>([]);
  const [canon, setCanon] = useState<CanonEntry[]>([]);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [premise, setPremise] = useState("");
  const [threadTitle, setThreadTitle] = useState("");
  const [canonCategory, setCanonCategory] = useState("OBJECT");
  const [canonStatement, setCanonStatement] = useState("");

  const refresh = () => {
    listEpisodeHistory(seriesId).then(setEpisodes).catch(() => setEpisodes([]));
    listThreads(seriesId).then(setThreads).catch(() => setThreads([]));
    listCanon(seriesId).then(setCanon).catch(() => setCanon([]));
  };

  useEffect(() => {
    getSeries(seriesId)
      .then(setSeries)
      .catch((e) => setError(e instanceof Error ? e.message : "load failed"));
    refresh();
  }, [seriesId]);

  const onCreateEpisode = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createEpisode(seriesId, { title, premise });
      setTitle("");
      setPremise("");
      refresh();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "episode create failed");
    }
  };

  const onCreateThread = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createThread(seriesId, { title: threadTitle });
      setThreadTitle("");
      refresh();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "thread create failed");
    }
  };

  const onResolveThread = async (thread: StoryThread) => {
    const ep = episodes.find((e) => e.episode_number === episodes.length);
    if (!ep) {
      setError("resolve: no episode available in this series yet");
      return;
    }
    try {
      await resolveThread(thread.id, ep.id);
      refresh();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "resolve failed");
    }
  };

  const onCreateCanon = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createCanon(seriesId, { category: canonCategory, statement: canonStatement });
      setCanonStatement("");
      refresh();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "canon create failed");
    }
  };

  if (error && !series) return <main style={{ padding: 24 }}>{error}</main>;
  if (!series) return <main style={{ padding: 24 }}>loading…</main>;

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 860 }}>
      <p>
        <Link to="/series">← Series</Link>
      </p>
      <h1>
        {series.name} ({series.status})
      </h1>
      {series.status === "ACTIVE" && (
        <button
          onClick={() =>
            endSeries(seriesId)
              .then(() => getSeries(seriesId).then(setSeries))
              .catch((e) => setError(e instanceof Error ? e.message : "end failed"))
          }
        >
          end series
        </button>
      )}
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <h2>Episodes ({episodes.length})</h2>
      {episodes.length === 0 ? (
        <p>none yet</p>
      ) : (
        <ol>
          {episodes.map((e) => (
            <li key={e.id}>
              <Link to={`/episodes/${e.id}`}>Ep {e.episode_number}: {e.title}</Link>{" "}
              <small>[{e.status}]</small>
              <br />
              <small>{e.premise}</small>
            </li>
          ))}
        </ol>
      )}
      <form onSubmit={(e) => void onCreateEpisode(e)}>
        <input
          placeholder="episode title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />{" "}
        <input
          placeholder="premise"
          value={premise}
          onChange={(e) => setPremise(e.target.value)}
          style={{ width: "45%" }}
        />{" "}
        <button type="submit">add episode</button>
      </form>

      <h2>Story threads</h2>
      {threads.length === 0 ? (
        <p>none yet</p>
      ) : (
        <ul>
          {threads.map((t) => (
            <li key={t.id}>
              <strong>{t.status}</strong> — {t.title}
              {t.status === "OPEN" && (
                <>
                  {" "}
                  <button onClick={() => void onResolveThread(t)}>resolve w/ last ep</button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={(e) => void onCreateThread(e)}>
        <input
          placeholder="unresolved thread (e.g. Hank promised never to buy an AI tractor)"
          value={threadTitle}
          onChange={(e) => setThreadTitle(e.target.value)}
          style={{ width: "70%" }}
          required
        />{" "}
        <button type="submit">add thread</button>
      </form>

      <h2>Canon</h2>
      {canon.length === 0 ? (
        <p>no canon yet</p>
      ) : (
        <ul>
          {canon.map((c) => (
            <li key={c.id}>
              <strong>{c.category}</strong> — {c.statement}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={(e) => void onCreateCanon(e)}>
        <select
          value={canonCategory}
          onChange={(e) => setCanonCategory(e.target.value)}
        >
          {CANON_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>{" "}
        <input
          placeholder="canon statement"
          value={canonStatement}
          onChange={(e) => setCanonStatement(e.target.value)}
          style={{ width: "55%" }}
          required
        />{" "}
        <button type="submit">add canon</button>
      </form>
    </main>
  );
}
