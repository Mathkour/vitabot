export interface TopQuestionEntry {
  question: string;
  count: number;
}

export interface WeakAnswerEntry {
  question: string;
  count: number;
  last_seen: string;
}

export interface SatisfactionStats {
  thumbs_up: number;
  thumbs_down: number;
  total_rated: number;
  satisfaction_rate: number | null;
}

export interface TenantAnalyticsTimeseriesPoint {
  bucket: string;
  call_count: number;
  avg_response_time_ms: number;
}
