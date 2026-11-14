import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { LanguageService } from './language.service';
import { skipLoadingIndicator } from '../interceptors/loading-indicator.interceptor';
import { AskRequest, AskResponse, RateRequest, RateResponse } from '../models/chat.models';

@Injectable({ providedIn: 'root' })
export class ChatService {
  private readonly lang = inject(LanguageService);

  constructor(private readonly http: HttpClient) {}

  ask(payload: AskRequest): Observable<AskResponse> {
    // Asking a question must never trigger the global full-screen loading
    // overlay — the chat page's own UI is the only feedback the user should
    // see while this is in flight.
    return this.http.post<AskResponse>(`${environment.apiBaseUrl}/ask`, payload, {
      context: skipLoadingIndicator(),
    });
  }

  rate(payload: RateRequest): Observable<RateResponse> {
    return this.http.post<RateResponse>(`${environment.apiBaseUrl}/rate`, payload);
  }

  fetchMedia(url: string): Observable<Blob> {
    // Fires right after the bot's text answer has already rendered (see
    // chat-page.ts's processBotResponse), to quietly fill in an attached
    // image/video — without this, the global loading overlay would flash on
    // top of an answer the user can already see and is already reading.
    return this.http.get(url, { responseType: 'blob', context: skipLoadingIndicator() });
  }

  transcribe(audioBlob: Blob): Observable<{ text: string }> {
    // Voice flow has its own dedicated status bar (chat-page.ts's
    // voiceStatus/chat__voice-status) — the global overlay must stay out of
    // it the same way it already does for ask()/fetchMedia().
    const formData = new FormData();
    formData.append('file', audioBlob, 'audio.webm');
    // A hint so Arabic speech is transcribed as Arabic, never translated.
    formData.append('language', this.lang.lang());
    return this.http.post<{ text: string }>(
      `${environment.apiBaseUrl}/transcribe`,
      formData,
      { context: skipLoadingIndicator() },
    );
  }

  speak(text: string, languageCode: string): Observable<Blob> {
    // Fires right after the bot's text answer has already rendered (voice
    // questions auto-play the reply) — same reasoning as fetchMedia() above:
    // the answer is already visible, so the global overlay must not flash
    // on top of it while the TTS audio loads.
    return this.http.post(
      `${environment.apiBaseUrl}/speak`,
      { text, language_code: languageCode },
      { responseType: 'blob', context: skipLoadingIndicator() },
    );
  }
}
