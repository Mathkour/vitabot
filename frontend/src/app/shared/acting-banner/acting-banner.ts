import { Component, inject } from '@angular/core';
import { AdminSessionService } from '../../core/services/admin-session.service';
import { LanguageService } from '../../core/services/language.service';

@Component({
  selector: 'app-acting-banner',
  imports: [],
  templateUrl: './acting-banner.html',
  styleUrl: './acting-banner.scss',
})
export class ActingBanner {
  readonly adminSession = inject(AdminSessionService);
  readonly lang = inject(LanguageService);

  exit(): void {
    this.adminSession.exitTenant();
  }
}
