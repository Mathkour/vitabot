import { HttpClient } from '@angular/common/http';
import { Injectable, computed, signal } from '@angular/core';
import { Observable, catchError, map, of, switchMap, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import { skipLoadingIndicator } from '../interceptors/loading-indicator.interceptor';
import {
  AuthResponse,
  CurrentUser,
  JwtPayload,
  LoginRequest,
  UpdatePhoneResponse,
  UpdateUsernameResponse,
  UserRole,
} from '../models/auth.models';
import { TenantBranding } from '../models/tenant.models';
import { AdminSessionService } from './admin-session.service';
import { TenantThemeService } from './tenant-theme.service';

const ROLE_KEY = 'creditplus_role';
const EMAIL_KEY = 'creditplus_email';
const USERNAME_KEY = 'creditplus_username';
const PHONE_KEY = 'creditplus_phone';
const COUNTRY_CODE_KEY = 'creditplus_country_code';
const TENANT_ID_KEY = 'creditplus_tenant_id';
const COMPANY_ID_KEY = 'creditplus_company_id';

/** How long a successful verifySessionCached() result is trusted before the
 * next guard check re-verifies with the server — short enough that a dead
 * session is caught almost immediately, long enough that clicking through
 * several sidebar links in a row doesn't re-hit /auth/me on every single one. */
const VERIFY_CACHE_MS = 5000;

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly currentUserSignal = signal<CurrentUser>(this.readStoredUser());

  readonly currentUser = this.currentUserSignal.asReadonly();
  readonly isLoggedIn = computed(() => !!this.currentUserSignal().role);
  readonly isAdmin = computed(() => this.currentUserSignal().role === 'admin');
  readonly isSuperadmin = computed(() => this.currentUserSignal().role === 'superadmin');
  readonly isCompanyAdmin = computed(() => this.currentUserSignal().role === 'company_admin');

  /** Set by auth.interceptor.ts on a 401 that killed an active session; the
   * auth page reads and clears it once via consumeSessionExpired() so the
   * "please log in again" notice survives the redirect but doesn't linger
   * across a later, unrelated visit to /auth. */
  private readonly sessionExpiredSignal = signal(false);

  /** Timestamp (Date.now()) of the last successful verifySessionCached()
   * check, or 0 if none yet / the session was since torn down. Read by
   * verifySessionCached() to skip a redundant /auth/me round-trip on rapid
   * in-app navigations (see the route guards). */
  private lastVerifiedAt = 0;

  constructor(
    private readonly http: HttpClient,
    private readonly tenantTheme: TenantThemeService,
    private readonly adminSession: AdminSessionService,
  ) {}

  login(payload: LoginRequest): Observable<AuthResponse> {
    return this.http
      .post<AuthResponse>(`${environment.apiBaseUrl}/login`, payload)
      .pipe(tap((res) => this.handleAuthSuccess(res, payload.email)));
  }

  /**
   * Logs in from an already-issued access token (SSO landing page), rather
   * than a fresh email/password exchange. The token is the only thing the
   * browser ever sees for SSO — username/email/tenant_id/role all ride
   * along inside it, so they're decoded locally purely to populate UI
   * state; the token itself is never persisted to storage. It's first
   * exchanged with the backend so the httpOnly cookie gets set for this
   * browser (odoo-sso itself is a server-to-server call, so its response
   * never reaches here), then tenant branding is fetched as before.
   */
  loginWithToken(token: string): Observable<boolean> {
    const payload = this.decodeJwt(token);
    const role = payload?.role as UserRole | undefined;
    const tenantId = payload?.tenant_id as string | undefined;
    if (!payload || !role || !tenantId) {
      return of(false);
    }

    return this.http
      .post(`${environment.apiBaseUrl}/auth/session`, { token })
      .pipe(
        catchError(() => of(null)),
        switchMap(() =>
          this.http.get<TenantBranding>(`${environment.apiBaseUrl}/tenants/me/branding`).pipe(
            catchError(() => of(null)),
          ),
        ),
        tap((tenant) => {
          this.applySession({
            tenantId,
            companyId: (payload.company_id as string | undefined) ?? null,
            role,
            email: (payload.email as string | undefined) ?? null,
            username: (payload['username'] as string | undefined) ?? null,
            tenant,
          });
        }),
        map(() => true),
      );
  }

  /** Exchanges a short-lived, single-use Odoo-SSO code (the `?code=` the
   * /sso-login page receives) for the real access token, via a request
   * body rather than a URL — the token itself must never ride in a URL,
   * where it would leak through browser history, server/proxy access logs,
   * and the Referer header on whatever page is visited next. Returns null
   * if the code is invalid, already used, or expired (the exchange window
   * is only ~60s — a page refresh after that is expected to fail). */
  exchangeSsoCode(code: string): Observable<string | null> {
    return this.http
      .post<{ access_token: string }>(`${environment.apiBaseUrl}/auth/odoo-sso/exchange`, { code })
      .pipe(
        map((res) => res.access_token),
        catchError(() => of(null)),
      );
  }

  updateUsername(username: string): Observable<UpdateUsernameResponse> {
    return this.http
      .put<UpdateUsernameResponse>(`${environment.apiBaseUrl}/users/username`, { username })
      .pipe(
        tap((res) => {
          localStorage.setItem(USERNAME_KEY, res.username);
          this.currentUserSignal.update((user) => ({ ...user, username: res.username }));
        }),
      );
  }

  updatePhone(phone: string, countryCode: string): Observable<UpdatePhoneResponse> {
    return this.http
      .put<UpdatePhoneResponse>(`${environment.apiBaseUrl}/users/phone`, {
        phone,
        country_code: countryCode,
      })
      .pipe(
        tap((res) => {
          localStorage.setItem(PHONE_KEY, res.phone);
          localStorage.setItem(COUNTRY_CODE_KEY, res.country_code);
          this.currentUserSignal.update((user) => ({
            ...user,
            phone: res.phone,
            countryCode: res.country_code,
          }));
        }),
      );
  }

  logout(): void {
    this.http.post(`${environment.apiBaseUrl}/logout`, {}).subscribe({ error: () => {} });
    this.clearLocalSession();
  }

  /**
   * Local-only teardown, without the /logout network call — used when the
   * cookie is already dead (e.g. expired, per the 401 handling in
   * auth.interceptor.ts) so there's no live session left to ask the backend
   * to clear.
   */
  clearLocalSession(): void {
    this.lastVerifiedAt = 0;
    localStorage.removeItem(ROLE_KEY);
    localStorage.removeItem(EMAIL_KEY);
    localStorage.removeItem(USERNAME_KEY);
    localStorage.removeItem(PHONE_KEY);
    localStorage.removeItem(COUNTRY_CODE_KEY);
    localStorage.removeItem(TENANT_ID_KEY);
    localStorage.removeItem(COMPANY_ID_KEY);
    this.adminSession.reset();
    this.tenantTheme.resetTheme();
    this.currentUserSignal.set({
      email: null,
      username: null,
      phone: null,
      countryCode: null,
      role: null,
      tenantId: null,
      companyId: null,
    });
  }

  /** Called by auth.interceptor.ts when a 401 means the session itself died
   * (not just a rejected login attempt) — tears down local state without
   * the network /logout call, since the cookie is already invalid. */
  handleSessionExpired(): void {
    this.clearLocalSession();
    this.sessionExpiredSignal.set(true);
  }

  /** Reads and clears the session-expired flag in one step — call once from the auth page. */
  consumeSessionExpired(): boolean {
    const expired = this.sessionExpiredSignal();
    this.sessionExpiredSignal.set(false);
    return expired;
  }

  getTenantId(): string | null {
    return localStorage.getItem(TENANT_ID_KEY);
  }

  getCompanyId(): string | null {
    return localStorage.getItem(COMPANY_ID_KEY);
  }

  /**
   * Backend-verified check that the session cookie is still valid, called
   * once at app boot (see app.config.ts's APP_INITIALIZER). localStorage
   * alone can't tell us this: it survives a full browser close, but the
   * cookie is now a browser-session cookie by design (core/security.py's
   * set_auth_cookie has no max_age), so a fully-closed-then-reopened browser
   * (or a browser's own session-restore undermining that) can leave stale
   * "logged in" localStorage data pointing at a cookie that's actually gone.
   * If /auth/me 401s, that stale local data is cleared so the app falls
   * back to the login page instead of trying to render an authenticated
   * route with a dead session.
   */
  verifySession(): Observable<boolean> {
    if (!this.isLoggedIn()) {
      return of(true);
    }
    return this.http.get(`${environment.apiBaseUrl}/auth/me`, { context: skipLoadingIndicator() }).pipe(
      map(() => true),
      catchError(() => {
        this.clearLocalSession();
        return of(false);
      }),
    );
  }

  /**
   * Same server-verified check as verifySession(), used by the route guards
   * (admin/member/shared-page/superadmin) rather than reactively waiting for
   * some component's own API call to 401 — that reactive-only path left a
   * window where a dead session's destination route (sidebar, shell, etc.)
   * would render before the interceptor ever found out the session was
   * dead. Guards call this BEFORE letting navigation through, so a dead
   * session now gets redirected before the route's component ever mounts.
   *
   * A successful check is cached for VERIFY_CACHE_MS so clicking through
   * several sidebar links in a row doesn't re-hit /auth/me on every single
   * navigation — only a failure (or the cache expiring) triggers a fresh
   * server round-trip. The cache is intentionally never used to skip a
   * *failure* — only a prior success — so there's no way for it to paper
   * over a session that just died.
   */
  verifySessionCached(): Observable<boolean> {
    if (!this.isLoggedIn()) {
      return of(true);
    }
    if (Date.now() - this.lastVerifiedAt < VERIFY_CACHE_MS) {
      return of(true);
    }
    return this.verifySession().pipe(
      tap((ok) => {
        if (ok) this.lastVerifiedAt = Date.now();
      }),
    );
  }

  private handleAuthSuccess(res: AuthResponse, email: string): void {
    this.applySession({
      tenantId: res.tenant_id,
      companyId: res.company_id ?? null,
      role: res.role,
      email,
      username: res.username ?? null,
      phone: res.phone ?? null,
      countryCode: res.country_code ?? null,
      tenant: res.tenant,
    });
  }

  /** Writes profile fields (never the token itself) to storage and updates in-memory state. Shared by login() and loginWithToken(). */
  private applySession(params: {
    tenantId: string | null;
    companyId?: string | null;
    role: UserRole;
    email: string | null;
    username?: string | null;
    phone?: string | null;
    countryCode?: string | null;
    tenant?: TenantBranding | null;
  }): void {
    localStorage.setItem(ROLE_KEY, params.role);
    if (params.tenantId) {
      localStorage.setItem(TENANT_ID_KEY, params.tenantId);
    } else {
      localStorage.removeItem(TENANT_ID_KEY);
    }
    if (params.companyId) {
      localStorage.setItem(COMPANY_ID_KEY, params.companyId);
    } else {
      localStorage.removeItem(COMPANY_ID_KEY);
    }
    if (params.email) {
      localStorage.setItem(EMAIL_KEY, params.email);
    } else {
      localStorage.removeItem(EMAIL_KEY);
    }
    if (params.username) {
      localStorage.setItem(USERNAME_KEY, params.username);
    } else {
      localStorage.removeItem(USERNAME_KEY);
    }
    if (params.phone) {
      localStorage.setItem(PHONE_KEY, params.phone);
    } else {
      localStorage.removeItem(PHONE_KEY);
    }
    if (params.countryCode) {
      localStorage.setItem(COUNTRY_CODE_KEY, params.countryCode);
    } else {
      localStorage.removeItem(COUNTRY_CODE_KEY);
    }
    if (params.role === 'superadmin') {
      this.tenantTheme.applySuperadminTheme();
    } else {
      this.tenantTheme.applyBranding(params.tenant ?? null);
    }
    this.currentUserSignal.set({
      email: params.email,
      username: params.username ?? null,
      phone: params.phone ?? null,
      countryCode: params.countryCode ?? null,
      role: params.role,
      tenantId: params.tenantId,
      companyId: params.companyId ?? null,
    });

    // The caller just obtained this session from the server itself (a
    // successful /login response, or the /auth/session exchange in
    // loginWithToken) — mark it verified now so the route guard on the very
    // next navigation (login -> redirectAfterAuth -> the role's landing
    // page) hits verifySessionCached()'s cache instead of firing an
    // immediately-redundant GET /auth/me and adding a second full
    // round-trip to what's already the slowest part of signing in.
    this.lastVerifiedAt = Date.now();
  }

  /**
   * Restores UI session state on page load from the non-sensitive profile
   * fields left in localStorage. The access token itself lives in an
   * httpOnly cookie now and can't be read or expiry-checked from JS; if
   * that cookie is missing or expired, the backend will 401 on the first
   * authenticated request and the app treats that as logged-out then.
   */
  private readStoredUser(): CurrentUser {
    const role = localStorage.getItem(ROLE_KEY) as CurrentUser['role'];
    const email = localStorage.getItem(EMAIL_KEY);
    const username = localStorage.getItem(USERNAME_KEY);
    const phone = localStorage.getItem(PHONE_KEY);
    const countryCode = localStorage.getItem(COUNTRY_CODE_KEY);
    const tenantId = localStorage.getItem(TENANT_ID_KEY);
    const companyId = localStorage.getItem(COMPANY_ID_KEY);

    if (!role) {
      localStorage.removeItem(EMAIL_KEY);
      localStorage.removeItem(USERNAME_KEY);
      localStorage.removeItem(PHONE_KEY);
      localStorage.removeItem(COUNTRY_CODE_KEY);
      localStorage.removeItem(TENANT_ID_KEY);
      localStorage.removeItem(COMPANY_ID_KEY);
      return { email: null, username: null, phone: null, countryCode: null, role: null, tenantId: null, companyId: null };
    }

    return { email, username, phone, countryCode, role, tenantId, companyId };
  }

  private decodeJwt(token: string): JwtPayload | null {
    try {
      const base64Url = token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const json = decodeURIComponent(
        atob(base64)
          .split('')
          .map((c) => '%' + c.charCodeAt(0).toString(16).padStart(2, '0'))
          .join('')
      );
      return JSON.parse(json) as JwtPayload;
    } catch {
      return null;
    }
  }
}
