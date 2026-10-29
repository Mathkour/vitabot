import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  AiMonitoringErrorEntry,
  AiMonitoringSummary,
  AiMonitoringTimeseriesPoint,
} from '../models/ai-monitoring.models';

@Injectable({ providedIn: 'root' })
export class AiMonitoringService {
  constructor(private readonly http: HttpClient) {}

  getSummary(days: number): Observable<AiMonitoringSummary> {
    const params = new HttpParams().set('days', days);
    return this.http.get<AiMonitoringSummary>(
      `${environment.apiBaseUrl}/admin/ai-monitoring/summary`,
      { params },
    );
  }

  getTimeseries(days: number, interval: 'hour' | 'day' = 'day'): Observable<AiMonitoringTimeseriesPoint[]> {
    const params = new HttpParams().set('days', days).set('interval', interval);
    return this.http.get<AiMonitoringTimeseriesPoint[]>(
      `${environment.apiBaseUrl}/admin/ai-monitoring/timeseries`,
      { params },
    );
  }

  getErrors(limit = 50): Observable<AiMonitoringErrorEntry[]> {
    const params = new HttpParams().set('limit', limit);
    return this.http.get<AiMonitoringErrorEntry[]>(
      `${environment.apiBaseUrl}/admin/ai-monitoring/errors`,
      { params },
    );
  }
}
