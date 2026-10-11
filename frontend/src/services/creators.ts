import type { Creator, CreatorCreate, CreatorUpdate } from "../types/creator";

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
  return res.json() as Promise<T>;
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
