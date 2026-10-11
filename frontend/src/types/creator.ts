export interface Creator {
  id: number;
  name: string;
  slug: string;
  description: string;
  personality: string;
  values: string[];
  interests: string[];
  humor_style: string;
  visual_style: string;
  voice_style: string;
  goals: string[];
  constraints: string;
  system_prompt: string;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export type MemoryTypeName =
  | "CANON"
  | "EVENT"
  | "PREFERENCE"
  | "RELATIONSHIP"
  | "RUNNING_JOKE"
  | "CONTENT_LESSON"
  | "AUDIENCE_DISCOVERY";

export const MEMORY_TYPES: MemoryTypeName[] = [
  "CANON",
  "EVENT",
  "PREFERENCE",
  "RELATIONSHIP",
  "RUNNING_JOKE",
  "CONTENT_LESSON",
  "AUDIENCE_DISCOVERY",
];

export interface CreatorMemory {
  id: number;
  creator_id: number;
  type: MemoryTypeName;
  content: string;
  importance: number;
  confidence: number;
  created_at: string;
}

export interface CreatorVoice {
  creator_id: number;
  creator_name: string;
  text: string;
  model: string;
  prompt_version: string;
  provider: string;
  memories_used: string[];
}

export interface CreatorCreate {
  name: string;
  slug: string;
  description?: string;
  personality?: string;
  interests?: string[];
  humor_style?: string;
}

export type CreatorUpdate = Partial<
  Omit<Creator, "id" | "created_at" | "updated_at">
>;
