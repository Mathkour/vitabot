export interface OdooHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface OdooChartData {
  chart_type: 'bar' | 'pie';
  title: string;
  labels: string[];
  values: number[];
}

export interface OdooAskResponse {
  answer: string;
  chart: OdooChartData | null;
}

export interface OdooSuggestedQuestion {
  id: string;
  question: string;
  question_ar?: string | null;
}
