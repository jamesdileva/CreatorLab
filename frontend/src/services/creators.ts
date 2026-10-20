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

// creator familiarity (Sprint 11.2)
export interface CreatorFamiliarity {
  creator_id: number;
  creator_slug: string;
  viewer_count: number;
  tiers: { unknown: number; familiar: number; favorite: number };
  familiar_or_better: number;
  viewers: { viewer_id: number; handle: string; exposure: number; tier: string }[];
}

export const getFamiliarity = (creatorId: number): Promise<CreatorFamiliarity> =>
  req<CreatorFamiliarity>(`${BASE}/${creatorId}/familiarity`);

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

// relationships (Sprint 13.1)
export interface Relationship {
  id: number;
  creator_a_id: number;
  creator_b_id: number;
  friendship: number;
  rivalry: number;
  respect: number;
  annoyance: number;
  collaboration: number;
  note: string;
  updated_at: string;
}

export interface RelationshipEvent {
  id: number;
  relationship_id: number;
  event_type: string;
  deltas: Record<string, number>;
  note: string;
  created_at: string;
}

export const EVENT_TYPES = [
  "collaboration_success",
  "collaboration_failure",
  "rivalry_match",
  "prank",
  "reconciliation",
  "shared_victory",
];

export const listRelationships = (creatorId: number): Promise<Relationship[]> =>
  req<Relationship[]>(`${BASE}/${creatorId}/relationships`);

export const createRelationship = (
  aId: number,
  bId: number
): Promise<Relationship> =>
  req<Relationship>(`${BASE}/relationships`, {
    method: "POST",
    body: JSON.stringify({ creator_a_id: aId, creator_b_id: bId }),
  });

export const applyRelationshipEvent = (
  relationshipId: number,
  eventType: string,
  note = ""
): Promise<{ relationship: Relationship; event: RelationshipEvent }> =>
  req<{ relationship: Relationship; event: RelationshipEvent }>(
    `${BASE}/relationships/${relationshipId}/events`,
    { method: "POST", body: JSON.stringify({ event_type: eventType, note }) }
  );

export const listRelationshipEvents = (
  relationshipId: number
): Promise<RelationshipEvent[]> =>
  req<RelationshipEvent[]>(`${BASE}/relationships/${relationshipId}/events`);

// strategy evolution (Sprint 22.1)
const ROOT = env.VITE_API_URL ?? "http://localhost:8000";

export interface StrategyProfile {
  creator_id: number;
  topic_mix: string[];
  format_mix: string[];
  pacing: string;
  episode_structure: string;
  humor_style: string;
  revision: number;
  strategy_version: string;
  updated_at: string | null;
}

export interface StrategyEvidenceItem {
  source: string;
  n: number;
  ids: number[];
  value: string;
  detail: string;
}

export interface StrategyProposal {
  id: number;
  creator_id: number;
  dimension: string;
  current_value: unknown;
  proposed_value: unknown;
  rationale: string;
  evidence: StrategyEvidenceItem[];
  evidence_count: number;
  min_evidence: number;
  status: string;
  source_version: string;
  note: string;
  created_at: string | null;
  decided_at: string | null;
}

export interface CreatorStrategyView {
  strategy: StrategyProfile;
  dimensions: string[];
  evidence: Record<string, StrategyEvidenceItem[]>;
  proposals: StrategyProposal[];
}

export const getStrategyEvolution = (
  creatorId: number
): Promise<CreatorStrategyView> =>
  req<CreatorStrategyView>(`${ROOT}/api/strategy/creators/${creatorId}`);

export const proposeStrategyChanges = (
  creatorId: number
): Promise<StrategyProposal[]> =>
  req<StrategyProposal[]>(`${ROOT}/api/strategy/creators/${creatorId}/propose`, {
    method: "POST",
  });

export const decideStrategyProposal = (
  proposalId: number,
  approve: boolean,
  note = ""
): Promise<StrategyProposal> =>
  req<StrategyProposal>(`${ROOT}/api/strategy/proposals/${proposalId}/decide`, {
    method: "POST",
    body: JSON.stringify({ approve, note }),
  });

// character development (Sprint 22.2)
export interface CharacterTrait {
  creator_id: number;
  trait: string;
  value: string;
  stage: number;
  updated_at: string | null;
}

export interface CharacterDevelopment {
  id: number;
  creator_id: number;
  trait: string;
  from_value: string | null;
  to_value: string;
  reason: string;
  episode_id: number | null;
  source: string;
  created_at: string | null;
}

export interface CharacterArc {
  creator_id: number;
  traits: CharacterTrait[];
  arcs: {
    trait: string;
    current: string;
    stages: number;
    path: string[];
    text: string;
  }[];
  history: CharacterDevelopment[];
}

export const getCharacterArc = (creatorId: number): Promise<CharacterArc> =>
  req<CharacterArc>(`${ROOT}/api/character-development/creators/${creatorId}`);

export const defineCharacterTrait = (
  creatorId: number,
  trait: string,
  value: string
): Promise<CharacterTrait> =>
  req<CharacterTrait>(
    `${ROOT}/api/character-development/creators/${creatorId}/traits`,
    { method: "POST", body: JSON.stringify({ trait, value }) }
  );

export const recordCharacterDevelopment = (
  creatorId: number,
  payload: { trait: string; to_value: string; reason: string; episode_id?: number }
): Promise<CharacterDevelopment> =>
  req<CharacterDevelopment>(
    `${ROOT}/api/character-development/creators/${creatorId}/developments`,
    { method: "POST", body: JSON.stringify(payload) }
  );
