import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { skipLoadingIndicator } from '../interceptors/loading-indicator.interceptor';
import { AskIndexResponse, DocumentIndexPage, DocumentIndexSearchResult } from '../models/document-index.models';

@Injectable({ providedIn: 'root' })
export class DocumentIndexService {
  constructor(private readonly http: HttpClient) {}

  search(query: string): Observable<DocumentIndexSearchResult[]> {
    const params = new HttpParams().set('q', query);
    return this.http.get<DocumentIndexSearchResult[]>(
      `${environment.apiBaseUrl}/index/search`,
      { params },
    );
  }

  getPage(pageId: string): Observable<DocumentIndexPage> {
    return this.http.get<DocumentIndexPage>(`${environment.apiBaseUrl}/index/pages/${pageId}`);
  }

  ask(question: string): Observable<AskIndexResponse> {
    // Must never trigger the global full-screen loading overlay — the Ask AI
    // page's own typing-dots bubble is the only loading feedback it shows.
    return this.http.post<AskIndexResponse>(`${environment.apiBaseUrl}/index/ask`, { question }, {
      context: skipLoadingIndicator(),
    });
  }
}
