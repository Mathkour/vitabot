import { SafeResourceUrl, SafeUrl } from '@angular/platform-browser';

export interface AskMediaItem {
  type: 'video' | 'image' | 'link';
  filename: string;
  display_name?: string | null;
  display_name_ar?: string | null;
  description_ar?: string | null;
  url: string;
}

export interface AskRequest {
  question: string;
  conversation_id: string | null;
  category_id?: string | null;
}

export interface SlideSource {
  slide_numbers: number[];
  slide_range: string;
}

export interface AskResponse {
  conversation_id: string;
  message_id: string;
  answer: string;
  sources: string[];
  media: AskMediaItem | null;
  slide_source?: SlideSource | null;
  offer_support?: boolean;
}

export type RatingScore = 1 | -1;

export interface RateRequest {
  message_id: string;
  score: RatingScore;
  feedback: string | null;
}

export interface RateResponse {
  status: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'bot';
  text: string;
  sources?: string[];
  messageId?: string;
  rating?: RatingScore | null;
  media?: AskMediaItem | null;
  mediaSafeUrl?: SafeUrl;
  youtubeEmbedUrl?: SafeResourceUrl | null;
  speechObjectUrl?: string;
  slideSource?: SlideSource | null;
  offerSupport?: boolean;
}
