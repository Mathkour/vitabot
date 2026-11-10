import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Injector, inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

/**
 * The access token lives in an httpOnly cookie set by the backend, so it's
 * invisible to JS — this interceptor makes sure that cookie actually gets
 * sent (frontend and backend are on different origins) and, if a request
 * comes back 401 while the app thought it had an active session, treats
 * that as the session having died (expired/invalid cookie) rather than
 * leaving the user stuck on the page with a raw error. A 401 while NOT
 * logged in (e.g. a bad password on the login form itself) is left alone —
 * that's an ordinary rejected request, not a dead session.
 *
 * On a real session-death 401, this clears local session state and
 * navigates to /auth immediately — no confirmation modal, no click
 * required (there used to be a "session expired" modal here; it was
 * removed in favor of this automatic redirect, see SessionExpiredDialog's
 * git history if you need the old behavior back). The current URL is
 * preserved as a ?returnUrl= query param so a successful re-login lands the
 * user back where they were (see auth-page.ts's redirectAfterAuth).
 *
 * This is still needed even though the route guards (admin/member/shared-page
 * /superadmin) now verify the session server-side before letting navigation
 * through: guards only run at navigation time, so a session that dies WHILE
 * the user is already sitting on an already-guarded page (mid-use, no new
 * navigation) is only ever caught here, reactively, when that page's next
 * API call 401s.
 *
 * No explicit dedup is needed for several 401s arriving close together: the
 * `authService.isLoggedIn()` check below already goes false the moment the
 * first one clears local state, so any 401 that resolves afterward is
 * skipped — only a 401 landing in the same tick as the first could still
 * slip through, which just means navigate() is called twice with the same
 * target, which Angular's Router already no-ops.
 *
 * AuthService/Router are resolved lazily via Injector.get() inside the
 * catchError callback rather than injected up front — AuthService's own
 * constructor chain (via TenantThemeService) fires an HTTP request to fetch
 * branding, which runs through this very interceptor. Injecting AuthService
 * eagerly here means that first request's interceptor call would ask the
 * injector for AuthService while AuthService is still being constructed,
 * which Angular reports as a circular dependency (NG0200) and crashes the
 * whole app at boot — surfacing as a blank page. Injector.get(), unlike
 * inject(), has no "must run synchronously in an injection context"
 * restriction, so calling it later (after AuthService has long finished
 * constructing) sidesteps the cycle entirely.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const injector = inject(Injector);
  return next(req.clone({ withCredentials: true })).pipe(
    catchError((err: unknown) => {
      // /sso-login is actively exchanging a brand-new SSO token for a fresh
      // session (see sso-login.ts). A 401 from some unrelated request still
      // racing on a stale pre-existing cookie (e.g. TenantThemeService's own
      // boot-time fetch) must not hijack navigation to /auth out from under
      // it — that page owns its own success/failure handling and already
      // shows an explicit error state if the SSO exchange itself fails.
      const onSsoLoginPage = window.location.pathname.startsWith('/sso-login');
      if (err instanceof HttpErrorResponse && err.status === 401 && !onSsoLoginPage) {
        const authService = injector.get(AuthService);
        if (authService.isLoggedIn()) {
          const router = injector.get(Router);
          // window.location, not router.url: this 401 can come from a
          // request fired before the Router has finished its FIRST
          // navigation (e.g. the app-initializer's boot-time verifySession()
          // call on a cold load of an already-expired session) — at that
          // moment router.url is still its default "/", not the page the
          // user actually landed on. router.url would then build
          // returnUrl=/, and since "/" redirects straight back to /auth
          // (see app.routes.ts), the first post-login navigation silently
          // bounces back to /auth and drops the param — only a *second*
          // login (now with no returnUrl left) falls through to the normal
          // role-based default and actually lands the user anywhere. The
          // browser's own location is already correct at this point
          // regardless of Angular's bootstrap timing.
          const currentUrl = window.location.pathname + window.location.search;
          authService.handleSessionExpired();
          const isAlreadyOnAuthPage = currentUrl === '/auth' || currentUrl.startsWith('/auth?');
          router.navigate(
            ['/auth'],
            isAlreadyOnAuthPage ? undefined : { queryParams: { returnUrl: currentUrl } },
          );
        }
      }
      return throwError(() => err);
    }),
  );
};
