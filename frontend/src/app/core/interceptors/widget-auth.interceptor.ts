import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { environment } from '../../../environments/environment';
import { WidgetSessionService } from '../services/widget-session.service';

/** Sends the in-memory widget token as a Bearer header (no-op outside the widget). */
export const widgetAuthInterceptor: HttpInterceptorFn = (req, next) => {
  const token = inject(WidgetSessionService).token;
  if (token && req.url.startsWith(environment.apiBaseUrl)) {
    return next(req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
  }
  return next(req);
};
