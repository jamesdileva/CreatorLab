export type SeriesStatusName = "ACTIVE" | "ENDED";

export interface Series {
  id: number;
  creator_id: number;
  name: string;
  description: string;
  status: SeriesStatusName;
  created_at: string;
  updated_at: string;
}

export type EpisodeStatusName =
  | "IDEA"
  | "SIMULATION"
  | "REVIEW"
  | "APPROVED"
  | "RENDERING"
  | "READY"
  | "PUBLISHED"
  | "ARCHIVED";

export const EPISODE_STATUSES: EpisodeStatusName[] = [
  "IDEA",
  "SIMULATION",
  "REVIEW",
  "APPROVED",
  "RENDERING",
  "READY",
  "PUBLISHED",
  "ARCHIVED",
];

export interface Episode {
  id: number;
  creator_id: number;
  series_id: number;
  episode_number: number;
  title: string;
  premise: string;
  synopsis: string;
  script: string;
  status: EpisodeStatusName;
  created_at: string;
  updated_at: string;
}

export interface Scene {
  id: number;
  episode_id: number;
  scene_number: number;
  title: string;
  direction: string;
  created_at: string;
}

export type ThreadStatusName = "OPEN" | "RESOLVED" | "ABANDONED";

export interface StoryThread {
  id: number;
  series_id: number;
  title: string;
  description: string;
  status: ThreadStatusName;
  introduced_episode_id: number | null;
  resolved_episode_id: number | null;
  created_at: string;
}

export type CanonCategoryName =
  | "CHARACTER"
  | "LOCATION"
  | "OBJECT"
  | "EVENT"
  | "RELATIONSHIP"
  | "RUNNING_JOKE"
  | "OTHER";

export const CANON_CATEGORIES: CanonCategoryName[] = [
  "CHARACTER",
  "LOCATION",
  "OBJECT",
  "EVENT",
  "RELATIONSHIP",
  "RUNNING_JOKE",
  "OTHER",
];

export interface CanonEntry {
  id: number;
  series_id: number;
  category: CanonCategoryName;
  statement: string;
  created_at: string;
}
