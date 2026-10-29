import { inject } from '@angular/core';
import { CanDeactivateFn } from '@angular/router';
import { UploadLockService } from '../services/upload-lock.service';

export const uploadLockGuard: CanDeactivateFn<unknown> = () => {
  const uploadLock = inject(UploadLockService);
  return !uploadLock.isLocked();
};
