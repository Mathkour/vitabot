export type UnansweredQuestionStatus = 'open' | 'answered' | 'dismissed';

export interface UnansweredQuestion {
  id: string;
  question: string;
  status: UnansweredQuestionStatus;
  created_at: string;
  user_id: string | null;
  username: string | null;
  email: string | null;
  company_name: string | null;
  category_id: string | null;
  category_name: string | null;
  answer: string | null;
  answered_at: string | null;
  answered_by_name: string | null;
  times_asked: number;
}

export interface UnansweredQuestionPage {
  items: UnansweredQuestion[];
  total: number;
  counts: Record<UnansweredQuestionStatus, number>;
}

/** One of the signed-in user's own questions an admin has since answered (topbar bell). */
export interface AnsweredQuestionNotice {
  id: string;
  question: string;
  answer: string;
  answered_at: string;
  conversation_id: string | null;
}
