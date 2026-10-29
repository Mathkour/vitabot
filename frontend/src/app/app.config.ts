import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { routes } from './app.routes';
import { actingTenantInterceptor } from './core/interceptors/acting-tenant.interceptor';
import { authInterceptor } from './core/interceptors/auth.interceptor';
import { loadingIndicatorInterceptor } from './core/interceptors/loading-indicator.interceptor';
import { widgetAuthInterceptor } from './core/interceptors/widget-auth.interceptor';
import { AuthService } from './core/services/auth.service';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(
      withInterceptors([widgetAuthInterceptor, authInterceptor, actingTenantInterceptor, loadingIndicatorInterceptor]),
    ),
    // Verifies the session cookie server-side before any route renders, so a
    // browser that fully closed and lost its (now session-scoped) auth
    // cookie doesn't render an authenticated page off of stale localStorage.
    provideAppInitializer(() =>
      // The embedded widget has its own in-memory session and must not
      // touch (or clear) the main app's stored session on this origin.
      // /sso-login is skipped too: it's about to establish a brand new
      // session from the SSO token in the URL regardless of whatever stale
      // local session (if any) already exists, so checking the old one first
      // only adds a network round-trip (and, on a stale/expired cookie,
      // triggers clearLocalSession for no reason) before the SSO page even
      // gets to run.
      window.location.pathname.startsWith('/widget-chat') ||
        window.location.pathname.startsWith('/sso-login')
        ? Promise.resolve(true)
        : firstValueFrom(inject(AuthService).verifySession()),
    ),
  ],
};
