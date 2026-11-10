import { Component, inject } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { LanguageService } from '../../core/services/language.service';

@Component({
  selector: 'app-access-denied',
  imports: [],
  templateUrl: './access-denied.html',
  styleUrl: './access-denied.scss',
})
export class AccessDenied {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly lang = inject(LanguageService);

  goToSafety(): void {
    this.router.navigate([this.auth.isAdmin() ? '/dashboard' : '/chat']);
  }
}
