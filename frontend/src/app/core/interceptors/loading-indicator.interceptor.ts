import { HttpContext, HttpContextToken, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { finalize } from 'rxjs';
import { LoadingIndicatorService } from '../services/loading-indicator.service';

/**
 * Set on a request's HttpContext to keep it out of the global loading bar —
 * for silent background work (thumbnail preview fetches, branding refresh
 * on boot) where a page-wide "something is loading" signal would be noise
 * rather than useful feedback.
 */
export const SKIP_LOADING_INDICATOR = new HttpContextToken(() => false);

export function skipLoadingIndicator(): HttpContext {
  return new HttpContext().set(SKIP_LOADING_INDICATOR, true);
}

export const loadingIndicatorInterceptor: HttpInterceptorFn = (req, next) => {
  if (req.context.get(SKIP_LOADING_INDICATOR)) {
    return next(req);
  }

  const loading = inject(LoadingIndicatorService);
  loading.start();
  return next(req).pipe(finalize(() => loading.stop()));
};
