export interface AiMonitoringGroupStats {
  endpoint?: string;
  model_used?: string;
  total_calls: number;
  success_count: number;
  error_count: number;
  timeout_count: number;
  avg_response_time_ms: number;
  success_rate: number;
}

export interface AiMonitoringSummary {
  days: number;
  total_calls: number;
  success_count: number;
  error_count: number;
  timeout_count: number;
  success_rate: number;
  avg_response_time_ms: number;
  by_endpoint: AiMonitoringGroupStats[];
  by_model: AiMonitoringGroupStats[];
}

export interface AiMonitoringTimeseriesPoint {
  bucket: string;
  call_count: number;
  avg_response_time_ms: number;
  error_count: number;
}

export interface AiMonitoringErrorEntry {
  id: string;
  tenant_id: string | null;
  endpoint: string;
  model_used: string;
  error_message: string | null;
  created_at: string;
}
