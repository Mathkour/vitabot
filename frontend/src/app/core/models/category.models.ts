export interface Category {
  id: string;
  name: string;
  is_published?: boolean;
}

export type LinkType = 'youtube' | 'google_drive' | 'other';

export interface CategoryDocument {
  id: string;
  filename: string;
  display_name?: string | null;
  display_name_ar?: string | null;
  status: string;
  has_file?: boolean;
  is_spreadsheet?: boolean;
}

export interface CategoryMediaItem {
  id: string;
  filename: string;
  display_name?: string | null;
  display_name_ar?: string | null;
  media_type: string;
  description: string;
  description_ar?: string | null;
  url?: string | null;
  link_type?: LinkType;
  category_id?: string;
}

export interface CategoryContent {
  documents: CategoryDocument[];
  media: CategoryMediaItem[];
}

export interface SuggestedQuestion {
  id: string;
  question: string;
  answer: string;
  question_ar?: string | null;
  answer_ar?: string | null;
  /** Starred by an admin to show on the /chat welcome screen. */
  is_featured?: boolean;
  /** Only on /suggested-questions/featured results. */
  category_name?: string;
}
