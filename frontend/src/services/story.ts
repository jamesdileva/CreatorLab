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

// universe canon (Sprint 14.1)
export interface UniverseEntity {
  id: number;
  kind: string;
  name: string;
  statement: string;
  created_at: string;
}

export const listUniverse = (): Promise<UniverseEntity[]> =>
  req<UniverseEntity[]>(`${ROOT}/api/universe`);

export const createUniverseEntity = (payload: {
  kind: string;
  name: string;
  statement: string;
}): Promise<UniverseEntity> =>
  req<UniverseEntity>(`${ROOT}/api/universe`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const deleteUniverseEntity = (id: number): Promise<void> =>
  req<void>(`${ROOT}/api/universe/${id}`, { method: "DELETE" });

// cross-creator episodes (Sprint 13.2)
export interface CrossEpisodeResult {
  episode: Episode;
  draft: {
    participants: string[];
    premise: string;
    synopsis: string;
    scenes: Scene[];
    script: string;
  };
  evaluation_status: string;
  issues: { code: string; severity: string; detail: string }[];
  prompt_version: string;
  provider: string;
  model: string;
  cast_used: string[];
}

export const generateCrossEpisode = (
  seriesId: number,
  participantIds: number[]
): Promise<CrossEpisodeResult> =>
  req<CrossEpisodeResult>(
    `${ROOT}/api/series/${seriesId}/generate-cross-episode`,
    {
      method: "POST",
      body: JSON.stringify({ participant_ids: participantIds }),
    }
  );

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

// video rendering (Sprint 5.1)
export interface RenderResult {
  episode_id: number;
  status: string;
  video_url: string;
  captions_url: string;
  manifest_url: string;
  total_duration: number;
  scene_count: number;
  render_id: number;
}

export const renderEpisode = (id: number): Promise<RenderResult> =>
  req<RenderResult>(`${ROOT}/api/episodes/${id}/render`, {
    method: "POST",
    body: JSON.stringify({}),
  });

// approval gate (Sprint 5.3)
export const approveEpisode = (id: number): Promise<{ status: string }> =>
  req<{ status: string }>(`${ROOT}/api/episodes/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({}),
  });

export const rejectEpisode = (id: number): Promise<{ status: string }> =>
  req<{ status: string }>(`${ROOT}/api/episodes/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({}),
  });

export interface RenderRecord {
  id: number;
  episode_id: number;
  status: string;
  card_version: string;
  identity_version: string;
  total_duration: number;
  created_at: string;
}

export const listEpisodeRenders = (id: number): Promise<RenderRecord[]> =>
  req<RenderRecord[]>(`${ROOT}/api/episodes/${id}/renders`);

// private publish (Sprint 7.2)
export interface PublishedVideoRecord {
  id: number;
  episode_id: number;
  render_id: number;
  channel_id: string;
  video_id: string;
  title: string;
  privacy_status: string;
  status: string;
  youtube_status: string;
  attempts: number;
  total_duration: number;
  error: string;
  upload_time: string;
}

export const publishEpisode = (
  id: number,
  channelId?: string
): Promise<PublishedVideoRecord> =>
  req<PublishedVideoRecord>(`${ROOT}/api/youtube/episodes/${id}/publish`, {
    method: "POST",
    body: JSON.stringify(channelId ? { channel_id: channelId } : {}),
  });

export const listPublishedVideos = (): Promise<PublishedVideoRecord[]> =>
  req<PublishedVideoRecord[]>(`${ROOT}/api/youtube/videos`);

export const listEpisodeVideos = (id: number): Promise<PublishedVideoRecord[]> =>
  req<PublishedVideoRecord[]>(`${ROOT}/api/youtube/episodes/${id}/videos`);

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
