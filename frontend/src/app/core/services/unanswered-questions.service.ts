import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { skipLoadingIndicator } from '../interceptors/loading-indicator.interceptor';
import {
  AnsweredQuestionNotice,
  UnansweredQuestionPage,
  UnansweredQuestionStatus,
} from '../models/unanswered-question.models';

@Injectable({ providedIn: 'root' })
export class UnansweredQuestionsService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiBaseUrl}/unanswered-questions`;

  /** Open questions, for the sidebar badge — the page updates it on every load so it's never stale. */
  readonly openCountValue = signal(0);

  list(status: UnansweredQuestionStatus, page: number, pageSize: number, search = ''): Observable<UnansweredQuestionPage> {
    const params: Record<string, string> = { status, page: String(page), page_size: String(pageSize) };
    if (search.trim()) params['search'] = search.trim();
    return this.http.get<UnansweredQuestionPage>(this.base, { params });
  }

  refreshOpenCount(): void {
    this.http.get<{ count: number }>(`${this.base}/open-count`, { context: skipLoadingIndicator() }).subscribe({
      next: (res) => this.openCountValue.set(res.count),
      error: () => {},
    });
  }

  /** Answers or edits; also answers other open occurrences of the same question. */
  answer(id: string, answer: string, categoryId: string | null): Observable<{ status: string; updated: number }> {
    return this.http.post<{ status: string; updated: number }>(`${this.base}/${id}/answer`, {
      answer,
      category_id: categoryId,
    });
  }

  removeAnswer(id: string): Observable<{ status: string; updated: number }> {
    return this.http.delete<{ status: string; updated: number }>(`${this.base}/${id}/answer`);
  }

  dismiss(id: string): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.base}/${id}/dismiss`, {});
  }

  reopen(id: string): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.base}/${id}/reopen`, {});
  }

  // ── The asker's side (any signed-in user, own questions only) ──

  /** My questions an admin answered that I haven't seen yet. Polled by the topbar bell. */
  myNewAnswers(): Observable<AnsweredQuestionNotice[]> {
    return this.http.get<AnsweredQuestionNotice[]>(`${this.base}/me/answered`, { context: skipLoadingIndicator() });
  }

  /** Marks the given answers (or, with no ids, all of mine) as seen. */
  markAnswersSeen(ids?: string[]): Observable<{ updated: number }> {
    return this.http.post<{ updated: number }>(`${this.base}/me/answered/seen`, ids ? { ids } : {}, {
      context: skipLoadingIndicator(),
    });
  }
}
