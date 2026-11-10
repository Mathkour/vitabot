import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';
import { OdooAccessService } from '../services/odoo-access.service';

/** Ask Odoo only for users the backend says may use it — see OdooAccessService. */
export const odooAccessGuard: CanActivateFn = () => {
  const odooAccess = inject(OdooAccessService);
  const router = inject(Router);

  return odooAccess.check().pipe(map((allowed) => (allowed ? true : router.createUrlTree(['/access-denied']))));
};
