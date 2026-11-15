import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { skipLoadingIndicator } from '../interceptors/loading-indicator.interceptor';
import { SuggestedQuestion } from '../models/category.models';

@Injectable({ providedIn: 'root' })
export class SuggestedQuestionsService {
  constructor(private readonly http: HttpClient) {}

  /** `silent` keeps the request out of the page-wide loading overlay (the caller shows its own skeleton). */
  list(categoryId: string, silent = false): Observable<SuggestedQuestion[]> {
    return this.http.get<SuggestedQuestion[]>(
      `${environment.apiBaseUrl}/categories/${categoryId}/suggested-questions`,
      silent ? { context: skipLoadingIndicator() } : {},
    );
  }

  /** The questions admins starred for the chat welcome screen. */
  listFeatured(): Observable<SuggestedQuestion[]> {
    return this.http.get<SuggestedQuestion[]>(`${environment.apiBaseUrl}/suggested-questions/featured`, {
      context: skipLoadingIndicator(),
    });
  }

  setFeatured(id: string, isFeatured: boolean): Observable<void> {
    return this.http.put<void>(`${environment.apiBaseUrl}/suggested-questions/${id}/featured`, {
      is_featured: isFeatured,
    });
  }

  /** Counts a click — feeds the welcome screen's most-clicked slots. Fire-and-forget. */
  recordClick(id: string): Observable<void> {
    return this.http.post<void>(
      `${environment.apiBaseUrl}/suggested-questions/${id}/click`,
      {},
      { context: skipLoadingIndicator() },
    );
  }

  create(categoryId: string, question: string, answer: string): Observable<SuggestedQuestion> {
    return this.http.post<SuggestedQuestion>(`${environment.apiBaseUrl}/suggested-questions`, {
      category_id: categoryId,
      question,
      answer,
    });
  }

  update(id: string, question: string, answer: string): Observable<SuggestedQuestion> {
    return this.http.put<SuggestedQuestion>(
      `${environment.apiBaseUrl}/suggested-questions/${id}`,
      { question, answer },
    );
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${environment.apiBaseUrl}/suggested-questions/${id}`);
  }
}
