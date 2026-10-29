import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SuggestedQuestion } from '../models/category.models';

@Injectable({ providedIn: 'root' })
export class SuggestedQuestionsService {
  constructor(private readonly http: HttpClient) {}

  list(categoryId: string): Observable<SuggestedQuestion[]> {
    return this.http.get<SuggestedQuestion[]>(
      `${environment.apiBaseUrl}/categories/${categoryId}/suggested-questions`,
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
