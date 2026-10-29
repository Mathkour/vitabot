import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map, of } from 'rxjs';
import { AdminSessionService } from '../services/admin-session.service';
import { AuthService } from '../services/auth.service';

/**
 * Gate for pages that used to exist under BOTH /admin/* and /chat/* pointing
 * at the identical component (chat, profile, vita-insights, document-index)
 * — now that flattening the route tree collapsed each pair into a single
 * top-level route, there's no parent adminGuard/memberGuard left to enforce
 * "logged in, and not a superadmin who isn't acting as a tenant" the way
 * both parents did (adminGuard sent a non-acting superadmin to /superadmin;
 * memberGuard denied admin/superadmin outright). This reproduces that same
 * net restriction for the merged route.
 */
export const sharedPageGuard: CanActivateFn = (_route, state) => {
  const authService = inject(AuthService);
  const adminSession = inject(AdminSessionService);
  const router = inject(Router);

  if (!authService.isLoggedIn()) {
    return of(router.createUrlTree(['/auth'], { queryParams: { returnUrl: state.url } }));
  }

  // Server-verified before allowing navigation through — see admin.guard.ts
  // for why this can't be a synchronous localStorage-only check anymore.
  return authService.verifySessionCached().pipe(
    map((sessionValid) => {
      if (!sessionValid) {
        return router.createUrlTree(['/auth'], { queryParams: { returnUrl: state.url } });
      }
      if (authService.isSuperadmin() && !adminSession.isActing()) {
        return router.createUrlTree(['/superadmin']);
      }
      // company_admin's only granted scope is managing their own company's
      // users (/users, via companyAdminGuard) — these shared pages
      // (chat/profile/vita-insights/document-index) are outside that, so
      // explicitly denied rather than defaulting to "allowed" the way every
      // role that existed before company_admin implicitly did.
      if (authService.isCompanyAdmin()) {
        return router.createUrlTree(['/access-denied']);
      }
      return true;
    }),
  );
};
