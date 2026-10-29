import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  SatisfactionStats,
  TenantAnalyticsTimeseriesPoint,
  TopQuestionEntry,
  WeakAnswerEntry,
} from '../models/tenant-analytics.models';

@Injectable({ providedIn: 'root' })
export class TenantAnalyticsService {
  constructor(private readonly http: HttpClient) {}

  getTopQuestions(days: number, limit = 20): Observable<TopQuestionEntry[]> {
    const params = new HttpParams().set('days', days).set('limit', limit);
    return this.http.get<TopQuestionEntry[]>(`${environment.apiBaseUrl}/analytics/top-questions`, { params });
  }

  getWeakAnswers(days: number, limit = 20): Observable<WeakAnswerEntry[]> {
    const params = new HttpParams().set('days', days).set('limit', limit);
    return this.http.get<WeakAnswerEntry[]>(`${environment.apiBaseUrl}/analytics/weak-answers`, { params });
  }

  getSatisfaction(days: number): Observable<SatisfactionStats> {
    const params = new HttpParams().set('days', days);
    return this.http.get<SatisfactionStats>(`${environment.apiBaseUrl}/analytics/satisfaction`, { params });
  }

  getTimeseries(days: number, interval: 'hour' | 'day' = 'day'): Observable<TenantAnalyticsTimeseriesPoint[]> {
    const params = new HttpParams().set('days', days).set('interval', interval);
    return this.http.get<TenantAnalyticsTimeseriesPoint[]>(`${environment.apiBaseUrl}/analytics/timeseries`, { params });
  }
}
