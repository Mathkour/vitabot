import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  ActivityLogEntry,
  AnswerFeedbackPage,
  CompanyAnalyticsRow,
  ConversationSearchHit,
  ConversationSearchParams,
  DashboardSummary,
  FeedbackStatus,
} from '../models/admin-overview.models';

/** Dashboard, Answer Feedback, Activity Log, conversation search and per-company analytics. */
@Injectable({ providedIn: 'root' })
export class AdminOverviewService {
  private readonly http = inject(HttpClient);
  private readonly api = environment.apiBaseUrl;

  dashboard(days: number): Observable<DashboardSummary> {
    return this.http.get<DashboardSummary>(`${this.api}/dashboard/summary`, { params: { days } });
  }

  feedback(status: FeedbackStatus, page: number, pageSize: number, search = ''): Observable<AnswerFeedbackPage> {
    const params: Record<string, string | number> = { status, page, page_size: pageSize };
    if (search.trim()) params['search'] = search.trim();
    return this.http.get<AnswerFeedbackPage>(`${this.api}/answer-feedback`, { params });
  }

  fixFeedback(id: string, answer: string, categoryId: string | null): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.api}/answer-feedback/${id}/fix`, { answer, category_id: categoryId });
  }

  dismissFeedback(id: string): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.api}/answer-feedback/${id}/dismiss`, {});
  }

  deleteFeedback(id: string): Observable<{ status: string }> {
    return this.http.delete<{ status: string }>(`${this.api}/answer-feedback/${id}`);
  }

  reopenFeedback(id: string): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.api}/answer-feedback/${id}/reopen`, {});
  }

  activityLog(page: number, pageSize: number, search = '', area = ''): Observable<{ items: ActivityLogEntry[]; total: number }> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (search.trim()) params['search'] = search.trim();
    if (area) params['area'] = area;
    return this.http.get<{ items: ActivityLogEntry[]; total: number }>(`${this.api}/activity-log`, { params });
  }

  searchConversations(p: ConversationSearchParams, pageSize = 20): Observable<{ items: ConversationSearchHit[]; total: number }> {
    const params: Record<string, string | number | boolean> = { page: p.page, page_size: pageSize };
    if (p.q?.trim()) params['q'] = p.q.trim();
    if (p.dateFrom) params['date_from'] = p.dateFrom;
    if (p.dateTo) params['date_to'] = p.dateTo;
    if (p.companyId) params['company_id'] = p.companyId;
    if (p.onlyDisliked) params['only_disliked'] = true;
    return this.http.get<{ items: ConversationSearchHit[]; total: number }>(`${this.api}/conversations/search`, { params });
  }

  companyAnalytics(days: number): Observable<CompanyAnalyticsRow[]> {
    return this.http.get<CompanyAnalyticsRow[]>(`${this.api}/analytics/companies`, { params: { days } });
  }
}

/** Downloads rows as a UTF-8 CSV (with BOM so Excel shows Arabic correctly). */
export function downloadCsv(filename: string, header: string[], rows: (string | number | null)[][]): void {
  const cell = (v: string | number | null) => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [header, ...rows].map((r) => r.map(cell).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
