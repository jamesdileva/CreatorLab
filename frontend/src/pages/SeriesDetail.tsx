import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ConceptRanking from "../components/ConceptRanking";
import {
  createCanon,
  createEpisode,
  createThread,
  endSeries,
  generateConcepts,
  generateEpisode,
  listCanon,
  listConceptSets,
  listConcepts,
  listEpisodeHistory,
  listThreads,
  resolveThread,
} from "../services/story";
import { CANON_CATEGORIES } from "../types/story";
import type { CanonEntry, Episode, StoryThread } from "../types/story";
import type {
  Concept,
  ConceptSetSummary,
  GeneratedConcepts,
  GeneratedEpisode,
} from "../services/story";
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
  const [lastGenerated, setLastGenerated] = useState<GeneratedEpisode | null>(null);
  const [generating, setGenerating] = useState(false);
  const [topic, setTopic] = useState("");
  const [conceptCount, setConceptCount] = useState("5");
  const [conceptResult, setConceptResult] = useState<GeneratedConcepts | null>(null);
  const [conceptSets, setConceptSets] = useState<ConceptSetSummary[]>([]);
  const [openSetId, setOpenSetId] = useState<number | null>(null);
  const [openSetConcepts, setOpenSetConcepts] = useState<Concept[]>([]);

  const onGenerateEpisode = async () => {
    setGenerating(true);
    try {
      const result = await generateEpisode(seriesId, episodes.length);
      setLastGenerated(result);
      refresh();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const refresh = () => {
    listEpisodeHistory(seriesId).then(setEpisodes).catch(() => setEpisodes([]));
    listThreads(seriesId).then(setThreads).catch(() => setThreads([]));
    listCanon(seriesId).then(setCanon).catch(() => setCanon([]));
    listConceptSets(seriesId).then(setConceptSets).catch(() => setConceptSets([]));
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

  const onGenerateConcepts = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const result = await generateConcepts(seriesId, topic, Number(conceptCount));
      setConceptResult(result);
      refresh();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "concept generation failed");
    }
  };

  const onOpenConceptSet = (setId: number) => {
    setOpenSetId(setId);
    listConcepts(setId)
      .then(setOpenSetConcepts)
      .catch(() => setOpenSetConcepts([]));
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

      <h2>Generate episode (Sprint 2.2)</h2>
      <p style={{ fontSize: 12, color: "#555" }}>
        Retrieves series canon + creator memory + episode history, drafts an
        episode, evaluates it (PASS/REVIEW/BLOCK), and persists it as IDEA.
      </p>
      <button
        disabled={generating || series.status !== "ACTIVE"}
        onClick={() => void onGenerateEpisode()}
      >
        {generating ? "generating…" : "generate next episode"}
      </button>
      {lastGenerated && (
        <div
          style={{
            border: "1px solid #ccc",
            borderRadius: 8,
            padding: 12,
            marginTop: 8,
          }}
        >
          <p style={{ whiteSpace: "pre-wrap" }}>
            <strong>{lastGenerated.evaluation_status}</strong> — Ep{" "}
            {lastGenerated.episode.episode_number}: {lastGenerated.draft.premise}
          </p>
          {lastGenerated.resolved_threads.map((t) => (
            <p key={t}>
              <strong>resolved thread:</strong> {t}
            </p>
          ))}
          <p>{lastGenerated.draft.synopsis}</p>
          <ul>
            {lastGenerated.draft.scenes.map((s, i) => (
              <li key={i}>
                {s.title} — {s.direction}
              </li>
            ))}
          </ul>
          <small>
            prompt: {lastGenerated.prompt_version} · model: {lastGenerated.model} ·
            canon used: {lastGenerated.canon_used.length}
          </small>
          {lastGenerated.issues.length > 0 && (
            <ul>
              {lastGenerated.issues.map((i, idx) => (
                <li key={idx} style={{ color: "crimson" }}>
                  {i.severity}: {i.code} — {i.detail}
                </li>
              ))}
            </ul>
          )}
          <p>
            <Link to={`/episodes/${lastGenerated.episode.id}`}>
              open episode detail →
            </Link>
          </p>
        </div>
      )}

      <h2>Story threads</h2>
      {threads.length === 0 ? (
        <p>none yet</p>
      ) : (
        <ul>
          {threads.map((t) => {
            const introEp = episodes.find((e) => e.id === t.introduced_episode_id);
            const resolvedEp = episodes.find((e) => e.id === t.resolved_episode_id);
            return (
              <li key={t.id}>
                <strong>{t.status}</strong> — {t.title}
                {introEp && <> (introduced Ep {introEp.episode_number})</>}
                {resolvedEp && <> (resolved Ep {resolvedEp.episode_number})</>}
                {t.status === "OPEN" && (
                  <>
                    {" "}
                    <button onClick={() => void onResolveThread(t)}>resolve w/ last ep</button>
                  </>
                )}
              </li>
            );
          })}
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

      <h2>Candidate concepts (Sprint 3.1)</h2>
      <form onSubmit={(e) => void onGenerateConcepts(e)}>
        <input
          placeholder="topic (e.g. AI tractors)"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          required
        />{" "}
        <input
          type="number"
          min={3}
          max={10}
          value={conceptCount}
          onChange={(e) => setConceptCount(e.target.value)}
          style={{ width: 56 }}
        />{" "}
        <button type="submit">generate concepts</button>
      </form>
      {conceptResult && (
        <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 12 }}>
          <p>
            <strong>{conceptResult.evaluation_status}</strong> — {conceptResult.concepts.length}{" "}
            concepts · prompt {conceptResult.prompt_version} · model {conceptResult.model}
          </p>
          {conceptResult.issues.map((i, idx) => (
            <p key={idx} style={{ color: "crimson" }}>
              {i.severity}: {i.code} — {i.detail}
            </p>
          ))}
          <ol>
            {conceptResult.concepts.map((c) => (
              <li key={c.id}>
                <strong>{c.title}</strong>
                <br />
                {c.premise}
                <br />
                <small>
                  hook: {c.hook} · angle: {c.angle} · tags: {c.tags}
                </small>
              </li>
            ))}
          </ol>
          <ConceptRanking key={conceptResult.set.id} concepts={conceptResult.concepts} />
        </div>
      )}
      {conceptSets.length > 0 && (
        <>
          <h3>Previous concept sets</h3>
          <ul>
            {conceptSets.map((s) => (
              <li key={s.id}>
                {s.topic} ({s.created_at}){" "}
                <button onClick={() => onOpenConceptSet(s.id)}>
                  {openSetId === s.id ? "shown" : "show"}
                </button>
              </li>
            ))}
          </ul>
          {openSetId !== null && (
            <ol>
              {openSetConcepts.map((c) => (
                <li key={c.id}>
                  <strong>{c.title}</strong> — {c.premise}
                </li>
              ))}
            </ol>
          )}
        </>
      )}

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
