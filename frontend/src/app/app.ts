import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { ActingBanner } from './shared/acting-banner/acting-banner';
import { ConfirmDialog } from './shared/confirm-dialog/confirm-dialog';
import { LoadingBar } from './shared/loading-bar/loading-bar';
import { UploadLockOverlay } from './shared/upload-lock-overlay/upload-lock-overlay';

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    ActingBanner,
    ConfirmDialog,
    UploadLockOverlay,
    LoadingBar,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {}
