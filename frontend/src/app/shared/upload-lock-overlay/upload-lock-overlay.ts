import { Component, inject } from '@angular/core';
import { LanguageService } from '../../core/services/language.service';
import { UploadLockService } from '../../core/services/upload-lock.service';

@Component({
  selector: 'app-upload-lock-overlay',
  imports: [],
  templateUrl: './upload-lock-overlay.html',
  styleUrl: './upload-lock-overlay.scss',
})
export class UploadLockOverlay {
  readonly uploadLock = inject(UploadLockService);
  readonly lang = inject(LanguageService);

  cancel(): void {
    this.uploadLock.cancel();
  }
}
