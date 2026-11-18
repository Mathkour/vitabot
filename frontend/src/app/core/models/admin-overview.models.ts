export interface DashboardSummary {
  days: number;
  questions: number;
  questions_prev: number;
  active_users: number;
  /** All-time totals, not limited to the selected period. */
  total_companies: number;
  total_users: number;
  answered_rate: number | null;
  unanswered_in_period: number;
  satisfaction_rate: number | null;
  ratings_up: number;
  ratings_down: number;
  open_unanswered: number;
  pending_tickets: number;
  feedback_to_review: number;
  daily: { day: string; count: number }[];
  recent_unanswered: { id: string; question: string; created_at: string; user: string | null; company_name: string | null }[];
  recent_feedback: { id: string; question: string | null; answer: string; feedback: string | null; created_at: string }[];
  top_companies: { name: string; questions: number }[];
}

export type FeedbackStatus = 'open' | 'fixed' | 'dismissed';

export interface AnswerFeedbackItem {
  id: string;
  question: string | null;
  answer: string;
  feedback: string | null;
  created_at: string;
  review_status: FeedbackStatus;
  reviewed_at: string | null;
  reviewed_by_name: string | null;
  corrected_answer: string | null;
  question_id: string | null;
  user_id: string | null;
  username: string | null;
  email: string | null;
  company_name: string | null;
}

export interface AnswerFeedbackPage {
  items: AnswerFeedbackItem[];
  total: number;
  counts: Record<FeedbackStatus, number>;
}

export interface ActivityLogEntry {
  id: string;
  action: string;
  summary: string;
  created_at: string;
  user_name: string | null;
}

export interface ConversationSearchHit {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  conversation_id: string;
  score: number | null;
  user_id: string | null;
  username: string | null;
  email: string | null;
  company_name: string | null;
}

export interface ConversationSearchParams {
  q?: string;
  dateFrom?: string;
  dateTo?: string;
  companyId?: string;
  onlyDisliked?: boolean;
  page: number;
}

export interface CompanyAnalyticsRow {
  company_id: string | null;
  name: string | null;
  users: number;
  active_users: number;
  questions: number;
  unanswered: number;
  thumbs_up: number;
  thumbs_down: number;
}
