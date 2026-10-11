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

export interface CreatorVoice {
  creator_id: number;
  creator_name: string;
  text: string;
  model: string;
  prompt_version: string;
  provider: string;
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
