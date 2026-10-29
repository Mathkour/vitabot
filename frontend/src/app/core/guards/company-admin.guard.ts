import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map, of } from 'rxjs';
import { AdminSessionService } from '../services/admin-session.service';
import { AuthService } from '../services/auth.service';

/**
 * Like adminGuard, but also admits 'company_admin' — used ONLY on /users,
 * which a company_admin needs for managing their own company's users (the
 * backend scopes what they can actually see/touch there; see
 * require_admin_or_company_admin in core/auth.py). Every other admin page
 * (knowledge-base, documents, etc.) stays on the plain adminGuard, which
 * does not admit company_admin.
 */
export const companyAdminGuard: CanActivateFn = (_route, state) => {
  const authService = inject(AuthService);
  const adminSession = inject(AdminSessionService);
  const router = inject(Router);

  if (!authService.isLoggedIn()) {
    return of(router.createUrlTree(['/auth'], { queryParams: { returnUrl: state.url } }));
  }

  return authService.verifySessionCached().pipe(
    map((sessionValid) => {
      if (!sessionValid) {
        return router.createUrlTree(['/auth'], { queryParams: { returnUrl: state.url } });
      }
      if (authService.isAdmin() || authService.isCompanyAdmin()) {
        return true;
      }
      if (authService.isSuperadmin()) {
        return adminSession.isActing() ? true : router.createUrlTree(['/superadmin']);
      }
      return router.createUrlTree(['/access-denied']);
    }),
  );
};
