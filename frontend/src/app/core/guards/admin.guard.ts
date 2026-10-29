import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map, of } from 'rxjs';
import { AdminSessionService } from '../services/admin-session.service';
import { AuthService } from '../services/auth.service';

export const adminGuard: CanActivateFn = (_route, state) => {
  const authService = inject(AuthService);
  const adminSession = inject(AdminSessionService);
  const router = inject(Router);

  // No cached session at all — redirect immediately, no need to ask the
  // server about a session that doesn't exist locally.
  if (!authService.isLoggedIn()) {
    return of(router.createUrlTree(['/auth'], { queryParams: { returnUrl: state.url } }));
  }

  // Server-verified before allowing navigation through — closes the gap
  // where a dead session's destination route used to render (sidebar and
  // all) before some component's own API call happened to 401 and only
  // then triggered a redirect (see auth.interceptor.ts).
  return authService.verifySessionCached().pipe(
    map((sessionValid) => {
      if (!sessionValid) {
        return router.createUrlTree(['/auth'], { queryParams: { returnUrl: state.url } });
      }
      if (authService.isAdmin()) {
        return true;
      }
      if (authService.isSuperadmin()) {
        return adminSession.isActing() ? true : router.createUrlTree(['/superadmin']);
      }
      return router.createUrlTree(['/access-denied']);
    }),
  );
};
