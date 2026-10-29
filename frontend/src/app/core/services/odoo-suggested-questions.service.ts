import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { OdooSuggestedQuestion } from '../models/odoo.models';

@Injectable({ providedIn: 'root' })
export class OdooSuggestedQuestionsService {
  constructor(private readonly http: HttpClient) {}

  list(): Observable<OdooSuggestedQuestion[]> {
    return this.http.get<OdooSuggestedQuestion[]>(`${environment.apiBaseUrl}/odoo/suggested-questions`);
  }

  add(question: string): Observable<OdooSuggestedQuestion> {
    return this.http.post<OdooSuggestedQuestion>(`${environment.apiBaseUrl}/odoo/suggested-questions`, {
      question,
    });
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${environment.apiBaseUrl}/odoo/suggested-questions/${id}`);
  }
}
