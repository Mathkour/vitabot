import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { TenantThemeService } from '../services/tenant-theme.service';

const VITA_CARE_TENANT_NAME = 'Vita Care';

export const vitaCareTenantGuard: CanActivateFn = () => {
  const tenantTheme = inject(TenantThemeService);
  const router = inject(Router);

  if (tenantTheme.tenantName() === VITA_CARE_TENANT_NAME) {
    return true;
  }

  return router.createUrlTree(['/access-denied']);
};
