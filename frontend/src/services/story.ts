import type { CanonEntry, Episode, Scene, Series, StoryThread } from "../types/story";

const env = import.meta.env as Record<string, string | undefined>;
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// series
export const listSeries = (creatorId?: number): Promise<Series[]> =>
  req<Series[]>(
    `${ROOT}/api/series${creatorId != null ? `?creator_id=${creatorId}` : ""}`
  );

export const getSeries = (id: number): Promise<Series> =>
  req<Series>(`${ROOT}/api/series/${id}`);

export const createSeries = (name: string, creatorId: number): Promise<Series> =>
  req<Series>(`${ROOT}/api/series`, {
    method: "POST",
    body: JSON.stringify({ name, creator_id: creatorId, description: "" }),
  });

export const endSeries = (id: number): Promise<Series> =>
  req<Series>(`${ROOT}/api/series/${id}`, { method: "DELETE" });

// episodes
export const listEpisodeHistory = (seriesId: number): Promise<Episode[]> =>
  req<Episode[]>(`${ROOT}/api/series/${seriesId}/episodes`);

export const createEpisode = (
  seriesId: number,
  payload: { title: string; premise?: string; synopsis?: string }
): Promise<Episode> =>
  req<Episode>(`${ROOT}/api/series/${seriesId}/episodes`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getEpisode = (id: number): Promise<Episode> =>
  req<Episode>(`${ROOT}/api/episodes/${id}`);

export const updateEpisode = (
  id: number,
  patch: { title?: string; premise?: string; synopsis?: string; script?: string; status?: string }
): Promise<Episode> =>
  req<Episode>(`${ROOT}/api/episodes/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

export const archiveEpisode = (id: number): Promise<Episode> =>
  req<Episode>(`${ROOT}/api/episodes/${id}`, { method: "DELETE" });

// scenes
export const listScenes = (episodeId: number): Promise<Scene[]> =>
  req<Scene[]>(`${ROOT}/api/episodes/${episodeId}/scenes`);

export const createScene = (
  episodeId: number,
  payload: { title?: string; direction?: string }
): Promise<Scene> =>
  req<Scene>(`${ROOT}/api/episodes/${episodeId}/scenes`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const deleteScene = (sceneId: number): Promise<void> =>
  req<void>(`${ROOT}/api/scenes/${sceneId}`, { method: "DELETE" });

// threads
export const listThreads = (seriesId: number): Promise<StoryThread[]> =>
  req<StoryThread[]>(`${ROOT}/api/series/${seriesId}/threads`);

export const createThread = (
  seriesId: number,
  payload: { title: string; description?: string; introduced_episode_id?: number }
): Promise<StoryThread> =>
  req<StoryThread>(`${ROOT}/api/series/${seriesId}/threads`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const resolveThread = (
  threadId: number,
  resolvedEpisodeId: number
): Promise<StoryThread> =>
  req<StoryThread>(`${ROOT}/api/threads/${threadId}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "RESOLVED", resolved_episode_id: resolvedEpisodeId }),
  });

export const deleteThread = (threadId: number): Promise<void> =>
  req<void>(`${ROOT}/api/threads/${threadId}`, { method: "DELETE" });

// canon
export const listCanon = (seriesId: number): Promise<CanonEntry[]> =>
  req<CanonEntry[]>(`${ROOT}/api/series/${seriesId}/canon`);

export const createCanon = (
  seriesId: number,
  payload: { category: string; statement: string }
): Promise<CanonEntry> =>
  req<CanonEntry>(`${ROOT}/api/series/${seriesId}/canon`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const deleteCanon = (canonId: number): Promise<void> =>
  req<void>(`${ROOT}/api/canon/${canonId}`, { method: "DELETE" });

// episode generation (Sprint 2.2)
export interface GeneratedEpisode {
  episode: Episode;
  draft: { premise: string; synopsis: string; scenes: Scene[]; script: string };
  evaluation_status: string;
  issues: { code: string; severity: string; detail: string }[];
  prompt_version: string;
  provider: string;
  model: string;
  canon_used: string[];
  memories_used: string[];
  resolved_threads: string[];
}

export const generateEpisode = (
  seriesId: number,
  variant: number
): Promise<GeneratedEpisode> =>
  req<GeneratedEpisode>(`${ROOT}/api/series/${seriesId}/generate-episode`, {
    method: "POST",
    body: JSON.stringify({ variant }),
  });

// concepts (Sprint 3.1)
export interface ConceptSetSummary {
  id: number;
  creator_id: number;
  series_id: number | null;
  topic: string;
  prompt_version: string;
  provider: string;
  model: string;
  created_at: string;
}

export interface Concept {
  id: number;
  set_id: number;
  index: number;
  title: string;
  premise: string;
  hook: string;
  angle: string;
  tags: string;
  created_at: string;
}

export interface GeneratedConcepts {
  set: ConceptSetSummary;
  concepts: Concept[];
  evaluation_status: string;
  issues: { code: string; severity: string; detail: string }[];
  prompt_version: string;
  provider: string;
  model: string;
}

export const listConceptSets = (seriesId: number): Promise<ConceptSetSummary[]> =>
  req<ConceptSetSummary[]>(`${ROOT}/api/series/${seriesId}/concept-sets`);

export const listConcepts = (setId: number): Promise<Concept[]> =>
  req<Concept[]>(`${ROOT}/api/concept-sets/${setId}/concepts`);

export const generateConcepts = (
  seriesId: number,
  topic: string,
  count: number
): Promise<GeneratedConcepts> =>
  req<GeneratedConcepts>(`${ROOT}/api/series/${seriesId}/generate-concepts`, {
    method: "POST",
    body: JSON.stringify({ topic, count }),
  });

// scoring + human comparison (Sprint 3.2)
export interface ScoredConcept {
  concept: Concept;
  rank: number;
  scores: Record<string, number>;
  composite: number;
}

export interface ScoreSetResult {
  set: ConceptSetSummary;
  scorer_version: string;
  ranked: ScoredConcept[];
}

export interface ConceptComparison {
  system_order: number[];
  human_order: number[];
  agreement: {
    top_1_match: boolean;
    top_3_overlap: number;
    directional_accuracy: number;
  };
  correlation: { spearman: number; kendall_tau: number };
  system_top: number;
  human_top: number;
  sample_size: number;
}

export const scoreConceptSet = (setId: number): Promise<ScoreSetResult> =>
  req<ScoreSetResult>(`${ROOT}/api/concept-sets/${setId}/score`, {
    method: "POST",
    body: JSON.stringify({}),
  });

export const recordHumanRanking = (
  setId: number,
  order: number[],
  note = ""
): Promise<unknown> =>
  req<unknown>(`${ROOT}/api/concept-sets/${setId}/human-ranking`, {
    method: "POST",
    body: JSON.stringify({ order, note }),
  });

export const getConceptComparison = (
  setId: number
): Promise<ConceptComparison | null> =>
  req<ConceptComparison | null>(`${ROOT}/api/concept-sets/${setId}/comparison`);
