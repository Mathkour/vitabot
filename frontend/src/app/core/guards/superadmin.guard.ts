import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map, of } from 'rxjs';
import { AuthService } from '../services/auth.service';

export const superadminGuard: CanActivateFn = (_route, state) => {
  const authService = inject(AuthService);
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
      if (authService.isSuperadmin()) {
        return true;
      }
      return router.createUrlTree([authService.isAdmin() ? '/dashboard' : '/chat']);
    }),
  );
};
