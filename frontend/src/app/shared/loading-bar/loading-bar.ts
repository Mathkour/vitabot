import { Component, computed, inject } from '@angular/core';
import { LoadingIndicatorService } from '../../core/services/loading-indicator.service';
import { UploadLockService } from '../../core/services/upload-lock.service';

@Component({
  selector: 'app-loading-bar',
  imports: [],
  templateUrl: './loading-bar.html',
  styleUrl: './loading-bar.scss',
})
export class LoadingBar {
  private readonly loading = inject(LoadingIndicatorService);
  private readonly uploadLock = inject(UploadLockService);

  // Never shown alongside the upload-lock overlay — that's already a
  // full-screen indicator for the same "something is in flight" idea, so
  // stacking this on top of it would just be a second, redundant spinner.
  readonly show = computed(() => this.loading.isLoading() && !this.uploadLock.isLocked());
}
