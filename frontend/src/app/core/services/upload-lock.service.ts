import { Injectable, computed, signal } from '@angular/core';

interface UploadLockState {
  filename: string;
  onCancel?: () => void;
}

@Injectable({ providedIn: 'root' })
export class UploadLockService {
  readonly state = signal<UploadLockState | null>(null);
  readonly isLocked = computed(() => this.state() !== null);

  constructor() {
    window.addEventListener('beforeunload', (event) => {
      if (!this.state()) return;
      event.preventDefault();
      event.returnValue = '';
    });
  }

  lock(filename: string, onCancel?: () => void): void {
    this.state.set({ filename, onCancel });
  }

  unlock(): void {
    this.state.set(null);
  }

  cancel(): void {
    this.state()?.onCancel?.();
  }
}
