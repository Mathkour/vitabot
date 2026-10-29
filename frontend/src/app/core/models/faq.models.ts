export interface FaqItem {
  id: string;
  question: string;
  answer: string;
  question_ar?: string | null;
  answer_ar?: string | null;
  category_id?: string | null;
  source?: 'faq' | 'error_solution';
}

export interface FaqCategory {
  id: string;
  name_ar: string;
  name_en: string;
  display_order: number;
  created_at: string;
}

/** GET /faq/grouped (no category_id): a lightweight per-category summary —
 * no FAQ text, just enough to render accordion headers with a count. Only
 * categories that have at least one FAQ/Error Solution assigned appear. */
export interface FaqCategorySummary {
  category_id: string;
  name_ar: string;
  name_en: string;
  display_order: number;
  total: number;
}

/** GET /faq/grouped?category_id=...&page=...: one category's FAQs, paginated
 * at page_size per page (10 by default) — fetched lazily when that
 * category's accordion section is opened. */
export interface FaqGroupPage {
  category_id: string;
  name_ar: string;
  name_en: string;
  display_order: number;
  page: number;
  total_pages: number;
  total: number;
  faqs: FaqItem[];
}
