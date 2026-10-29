import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { Observable, map, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import { skipLoadingIndicator } from '../interceptors/loading-indicator.interceptor';

export interface WidgetConfig {
  tenant: string;
  bot_name: string;
  tenant_name: string;
  icon_color: string;
  primary_color: string;
  logo_path: string | null;
  suggested_questions: string[];
}

interface WidgetVerifyResponse {
  access_token: string;
  expires_in: number;
  user: { username: string; email: string };
}

/**
 * Session for the embedded chat iframe. The access token is held in memory
 * only — never localStorage/cookies — because the iframe is third-party to
 * the host page (cookies are frequently blocked) and shares an origin with
 * the main cpbot app, whose stored session must not be touched.
 */
@Injectable({ providedIn: 'root' })
export class WidgetSessionService {
  private accessToken: string | null = null;

  readonly tenant = signal<string | null>(null);
  readonly username = signal<string | null>(null);

  constructor(private readonly http: HttpClient) {}

  get token(): string | null {
    return this.accessToken;
  }

  /** Exchanges the host site's signed JWT for a cpbot access token. */
  verify(tenant: string, partnerToken: string): Observable<void> {
    return this.http
      .post<WidgetVerifyResponse>(
        `${environment.apiBaseUrl}/widget/sso/verify`,
        { tenant, token: partnerToken },
        { context: skipLoadingIndicator() },
      )
      .pipe(
        tap((res) => {
          this.accessToken = res.access_token;
          this.tenant.set(tenant);
          this.username.set(res.user.username);
        }),
        map(() => undefined),
      );
  }

  loadConfig(tenant: string): Observable<WidgetConfig> {
    return this.http.get<WidgetConfig>(`${environment.apiBaseUrl}/widget/config`, {
      params: { tenant },
      context: skipLoadingIndicator(),
    });
  }

  clear(): void {
    this.accessToken = null;
  }
}
