import { Component, inject } from '@angular/core';
import { ConfirmDialogService } from '../../core/services/confirm-dialog.service';
import { LanguageService } from '../../core/services/language.service';

@Component({
  selector: 'app-confirm-dialog',
  imports: [],
  templateUrl: './confirm-dialog.html',
  styleUrl: './confirm-dialog.scss',
})
export class ConfirmDialog {
  readonly dialog = inject(ConfirmDialogService);
  readonly lang = inject(LanguageService);

  confirm(): void {
    this.dialog.resolve(true);
  }

  cancel(): void {
    this.dialog.resolve(false);
  }
}
