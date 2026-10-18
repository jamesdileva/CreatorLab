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

export interface EmulatorAccount {
  id: number;
  handle: string;
  display_name: string;
  kind: string;
  creator_id: number | null;
}

export interface EmulatorEngagement {
  views: number;
  likes: number;
  comments: number;
  score: number;
}

export interface EmulatorPost {
  id: number;
  author: string;
  author_display: string;
  episode_id: number | null;
  caption: string;
  created_at: string | null;
  engagement: EmulatorEngagement;
}

export interface EmulatorComment {
  id: number;
  author: string;
  author_display: string;
  parent_id: number | null;
  body: string;
  created_at: string | null;
}

export interface EmulatorPostDetail extends EmulatorPost {
  comments: EmulatorComment[];
}

export interface EmulatorProfile {
  handle: string;
  display_name: string;
  kind: string;
  creator_id: number | null;
  followers: number;
  following: number;
  post_count: number;
  posts: EmulatorPost[];
}

export const listAccounts = (): Promise<EmulatorAccount[]> =>
  req<EmulatorAccount[]>(`${ROOT}/api/emulator/accounts`);

export const syncCreatorAccounts = (): Promise<EmulatorAccount[]> =>
  req<EmulatorAccount[]>(`${ROOT}/api/emulator/accounts/sync`, {
    method: "POST",
    body: JSON.stringify({}),
  });

export const createAccount = (payload: {
  handle: string;
  display_name?: string;
  kind?: string;
}): Promise<EmulatorAccount> =>
  req<EmulatorAccount>(`${ROOT}/api/emulator/accounts`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getFeed = (handle?: string): Promise<EmulatorPost[]> =>
  req<EmulatorPost[]>(
    `${ROOT}/api/emulator/feed${handle ? `?handle=${encodeURIComponent(handle)}` : ""}`
  );

export const createPost = (payload: {
  author: string;
  caption: string;
  episode_id?: number | null;
}): Promise<EmulatorPostDetail> =>
  req<EmulatorPostDetail>(`${ROOT}/api/emulator/posts`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getPost = (id: number): Promise<EmulatorPostDetail> =>
  req<EmulatorPostDetail>(`${ROOT}/api/emulator/posts/${id}`);

export const addComment = (
  postId: number,
  payload: { author: string; body: string; parent_id?: number | null }
): Promise<EmulatorPostDetail> =>
  req<EmulatorPostDetail>(`${ROOT}/api/emulator/posts/${postId}/comments`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const recordView = (
  postId: number,
  payload: { account: string; watch_seconds?: number; liked?: boolean }
): Promise<EmulatorPostDetail> =>
  req<EmulatorPostDetail>(`${ROOT}/api/emulator/posts/${postId}/view`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const follow = (follower: string, followed: string): Promise<unknown> =>
  req<unknown>(`${ROOT}/api/emulator/follow`, {
    method: "POST",
    body: JSON.stringify({ follower, followed }),
  });

export const getProfile = (handle: string): Promise<EmulatorProfile> =>
  req<EmulatorProfile>(`${ROOT}/api/emulator/accounts/${encodeURIComponent(handle)}`);

export interface AgentActionRecord {
  step_index: number;
  action: string;
  target_id: number | null;
  handle: string | null;
  body: string;
  watch_seconds: number | null;
  liked: boolean | null;
  reasoning: string;
  observation: string;
  status: string;
  error: string;
}

export interface AgentSession {
  id: number;
  account_handle: string;
  goal: string;
  environment: string;
  provider: string;
  model: string;
  prompt_version: string;
  max_steps: number;
  step_count: number;
  stopped_reason: string;
  created_at: string | null;
  actions: AgentActionRecord[];
}

export interface AgentSessionSummary {
  id: number;
  account_handle: string;
  goal: string;
  provider: string;
  model: string;
  step_count: number;
  stopped_reason: string;
  created_at: string | null;
}

export const runAgent = (
  account: string,
  goal: string,
  maxSteps = 8
): Promise<AgentSession> =>
  req<AgentSession>(`${ROOT}/api/emulator/agent/run`, {
    method: "POST",
    body: JSON.stringify({ account, goal, max_steps: maxSteps }),
  });

export const listAgentSessions = (): Promise<AgentSessionSummary[]> =>
  req<AgentSessionSummary[]>(`${ROOT}/api/emulator/agent/sessions`);

export const getAgentSession = (id: number): Promise<AgentSession> =>
  req<AgentSession>(`${ROOT}/api/emulator/agent/sessions/${id}`);

