import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { LanguageService } from '../../../core/services/language.service';

@Component({
  selector: 'app-sso-login',
  imports: [],
  templateUrl: './sso-login.html',
  styleUrl: './sso-login.scss',
})
export class SsoLoginPage {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);

  readonly lang = inject(LanguageService);
  readonly failed = signal(false);

  constructor() {
    // Supports both generations of the Odoo module, since different live
    // instances run different versions: a hardened one redirects here with
    // ?code=... (a short-lived, single-use code — never the real token —
    // exchanged below via AuthService.exchangeSsoCode), an older one
    // redirects with ?token=... directly.
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const token = params.get('token');

    if (code) {
      this.authService.exchangeSsoCode(code).subscribe({
        next: (exchangedToken) => {
          if (exchangedToken) {
            this.signIn(exchangedToken);
          } else {
            this.failed.set(true);
          }
        },
        error: () => this.failed.set(true),
      });
    } else if (token) {
      this.signIn(token);
    } else {
      this.failed.set(true);
    }
  }

  private signIn(token: string): void {
    this.authService.loginWithToken(token).subscribe({
      next: (ok) => {
        if (ok) {
          this.router.navigateByUrl('/chat');
        } else {
          this.failed.set(true);
        }
      },
      error: () => this.failed.set(true),
    });
  }

  goToLogin(): void {
    this.router.navigate(['/auth']);
  }
}
