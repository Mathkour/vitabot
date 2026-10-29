import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AdminSessionService } from '../services/admin-session.service';

export const actingTenantInterceptor: HttpInterceptorFn = (req, next) => {
  const adminSession = inject(AdminSessionService);
  const actingTenantId = adminSession.actingTenantId();

  if (!actingTenantId) {
    return next(req);
  }

  const actingReq = req.clone({
    setHeaders: { 'X-Acting-Tenant': actingTenantId },
  });

  return next(actingReq);
};
