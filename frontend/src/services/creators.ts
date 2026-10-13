import type {
  Creator,
  CreatorCreate,
  CreatorMemory,
  CreatorUpdate,
  CreatorVoice,
} from "../types/creator";

const env = import.meta.env as Record<string, string | undefined>;
const BASE = `${env.VITE_API_URL ?? "http://localhost:8000"}/api/creators`;

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

export const listCreators = (activeOnly = true): Promise<Creator[]> =>
  req<Creator[]>(`${BASE}?active_only=${activeOnly}`);

export const getCreator = (id: string): Promise<Creator> =>
  req<Creator>(`${BASE}/${id}`);

export const createCreator = (payload: CreatorCreate): Promise<Creator> =>
  req<Creator>(BASE, { method: "POST", body: JSON.stringify(payload) });

export const updateCreator = (id: number, patch: CreatorUpdate): Promise<Creator> =>
  req<Creator>(`${BASE}/${id}`, { method: "PATCH", body: JSON.stringify(patch) });

export const deactivateCreator = (id: number): Promise<Creator> =>
  req<Creator>(`${BASE}/${id}`, { method: "DELETE" });

export const generateCreatorVoice = (
  id: number,
  user_message: string
): Promise<CreatorVoice> =>
  req<CreatorVoice>(`${BASE}/${id}/generate`, {
    method: "POST",
    body: JSON.stringify({ user_message }),
  });

export const listPromptVersions = (): Promise<string[]> =>
  req<string[]>(`${BASE}/prompts/versions`);

export const listMemories = (creatorId: number): Promise<CreatorMemory[]> =>
  req<CreatorMemory[]>(`${BASE}/${creatorId}/memories`);

export const createMemory = (
  creatorId: number,
  payload: { type: string; content: string; importance?: number; confidence?: number }
): Promise<CreatorMemory> =>
  req<CreatorMemory>(`${BASE}/${creatorId}/memories`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const deleteMemory = (creatorId: number, memoryId: number): Promise<void> =>
  req<void>(`${BASE}/${creatorId}/memories/${memoryId}`, { method: "DELETE" });

// performance memory (Sprint 10.1)
export interface PerformanceSummary {
  creator_id: number;
  episodes_with_metrics: number;
  overall_avg_views: number;
  sim_coverage: number;
  topics: Record<string, { episodes: number; avg_views: number; lift_vs_mean: number; verdict: string }>;
  structures: Record<string, { episodes: number; avg_views: number; lift_vs_mean: number; verdict: string }>;
}

export interface DistillResult {
  creator_id: number;
  memories_created: number;
  memories: { id: number; type: string; content: string }[];
}

export const getPerformance = (creatorId: number): Promise<PerformanceSummary> =>
  req<PerformanceSummary>(`${BASE}/${creatorId}/performance`);

export const distillPerformance = (creatorId: number): Promise<DistillResult> =>
  req<DistillResult>(`${BASE}/${creatorId}/distill-performance`, { method: "POST" });

// creator strategy (Sprint 10.2)
export interface StrategyObservation {
  scope: string;
  creator?: string;
  creators?: string[];
  kind: string;
  tag: string;
  verdict: string;
  episodes: number;
  text: string;
}

export interface CreatorStrategy {
  min_episodes: number;
  sufficient_creators: number;
  per_creator: Record<string, { creator_id: number; name: string; episodes_with_metrics: number; observations: StrategyObservation[] }>;
  shared: StrategyObservation[];
  interpretation_allowed: boolean;
}

export const getStrategy = (): Promise<CreatorStrategy> =>
  req<CreatorStrategy>(`${BASE}/strategy`);

// character visual identity (Sprint 5.2)
export interface CharacterIdentity {
  id: number;
  creator_id: number;
  display_name: string;
  palette: Record<string, string>;
  accessories: string[];
  props: string[];
  style: string;
  version: string;
}

export const getIdentity = (creatorId: string): Promise<CharacterIdentity> =>
  req<CharacterIdentity>(`${BASE}/${creatorId}/identity`);

export const updateIdentity = (
  creatorId: string,
  patch: { palette?: Record<string, string>; accessories?: string[]; display_name?: string }
): Promise<CharacterIdentity> =>
  req<CharacterIdentity>(`${BASE}/${creatorId}/identity`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
