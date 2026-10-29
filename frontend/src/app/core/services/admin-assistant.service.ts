import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { skipLoadingIndicator } from '../interceptors/loading-indicator.interceptor';

export interface AdminAskResponse {
  answer: string;
}

@Injectable({ providedIn: 'root' })
export class AdminAssistantService {
  constructor(private readonly http: HttpClient) {}

  ask(question: string): Observable<AdminAskResponse> {
    // Admin Assistant already shows its own typing-dots indicator while this
    // is in flight — see ChatService.ask()'s comment for why the global
    // overlay is explicitly skipped here rather than left to chance.
    return this.http.post<AdminAskResponse>(
      `${environment.apiBaseUrl}/admin/ask`,
      { question },
      { context: skipLoadingIndicator() },
    );
  }
}
