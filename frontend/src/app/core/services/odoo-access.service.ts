import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, map, of, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import { skipLoadingIndicator } from '../interceptors/loading-indicator.interceptor';

interface OdooAccessResponse {
  allowed: boolean;
  source: 'company' | 'vita_care' | null;
  reason: string | null;
}

/**
 * Whether the current user may use Ask Odoo — decided by the backend
 * (GET /odoo/access, same rule /odoo/ask enforces): a company user only with
 * their own company's Odoo connection, Vita Care's own staff (no company)
 * with Vita Care's Odoo. The links and route guard only mirror that answer;
 * the backend still refuses anyone else on its own.
 */
@Injectable({ providedIn: 'root' })
export class OdooAccessService {
  private readonly http = inject(HttpClient);

  readonly allowed = signal(false);

  /** Re-asks the backend and updates `allowed`; any error counts as "not allowed". */
  check(): Observable<boolean> {
    return this.http
      .get<OdooAccessResponse>(`${environment.apiBaseUrl}/odoo/access`, { context: skipLoadingIndicator() })
      .pipe(
        map((res) => res.allowed),
        catchError(() => of(false)),
        tap((allowed) => this.allowed.set(allowed)),
      );
  }

  /** Hides the link until the answer arrives, so a previous user's answer is never shown to the next one. */
  refresh(): void {
    this.allowed.set(false);
    this.check().subscribe();
  }
}
