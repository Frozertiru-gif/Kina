export type TitleType = "movie" | "series";

export interface Title {
  id: number;
  type: TitleType;
  name: string;
  original_name: string | null;
  description: string | null;
  year: number | null;
  poster_url: string | null;
  is_published: boolean;
}

export interface Season {
  id: number;
  season_number: number;
  name: string | null;
  episodes_count: number;
}

export interface TitleDetail extends Title {
  seasons: Season[];
  episodes_count: number;
  available_audio_ids: number[];
  available_quality_ids: number[];
}

export interface Episode {
  id: number;
  episode_number: number;
  name: string | null;
  published_at: string | null;
}

export interface WatchRequestPayload {
  title_id: number;
  episode_id: number | null;
  audio_id: number;
  quality_id: number;
}

export interface WatchResolvePayload {
  title_id: number;
  episode_id: number | null;
  audio_id: number | null;
  quality_id: number | null;
}

export interface WatchResolveResponse {
  variant_id: number;
  audio_id: number;
  quality_id: number;
}

export interface WatchResponse {
  mode: "direct" | "ad_gate";
  variant_id: number;
  title_id: number;
  episode_id: number | null;
}

export interface AuthResponse {
  id: number;
  tg_user_id: number;
  username: string | null;
  first_name: string | null;
  premium_until: string | null;
}

export interface ReferralInfo {
  code: string;
  link: string;
}
