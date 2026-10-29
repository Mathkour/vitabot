import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { TenantThemeService } from '../services/tenant-theme.service';

const HOUSING_BANK_TENANT_NAME = 'Housing Bank';

export const housingBankTenantGuard: CanActivateFn = () => {
  const tenantTheme = inject(TenantThemeService);
  const router = inject(Router);

  if (tenantTheme.tenantName() === HOUSING_BANK_TENANT_NAME) {
    return true;
  }

  return router.createUrlTree(['/access-denied']);
};
