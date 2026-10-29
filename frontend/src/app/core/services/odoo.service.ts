import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { skipLoadingIndicator } from '../interceptors/loading-indicator.interceptor';
import { OdooAskResponse, OdooHistoryMessage } from '../models/odoo.models';

@Injectable({ providedIn: 'root' })
export class OdooService {
  constructor(private readonly http: HttpClient) {}

  ask(question: string, history: OdooHistoryMessage[] = []): Observable<OdooAskResponse> {
    // Vita Insights already shows its own typing-dots indicator while this is
    // in flight — see ChatService.ask()'s comment for why the global
    // overlay is explicitly skipped here rather than left to chance.
    return this.http.post<OdooAskResponse>(
      `${environment.apiBaseUrl}/odoo/ask`,
      { question, history },
      { context: skipLoadingIndicator() },
    );
  }

  transcribe(audioBlob: Blob): Observable<{ text: string }> {
    const formData = new FormData();
    formData.append('file', audioBlob, 'audio.webm');
    return this.http.post<{ text: string }>(
      `${environment.apiBaseUrl}/transcribe`,
      formData,
    );
  }

  speak(text: string, languageCode: string, voice: string): Observable<Blob> {
    return this.http.post(
      `${environment.apiBaseUrl}/speak`,
      { text, language_code: languageCode, voice },
      { responseType: 'blob' },
    );
  }
}
