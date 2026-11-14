import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { LanguageService } from '../../../core/services/language.service';
import { ThemeService } from '../../../core/services/theme.service';
import { BrandFooter } from '../../../shared/brand-footer/brand-footer';
import { PasswordToggleDirective } from '../../../shared/directives/password-toggle.directive';

@Component({
  selector: 'app-auth-page',
  imports: [ReactiveFormsModule, PasswordToggleDirective, BrandFooter],
  templateUrl: './auth-page.html',
  styleUrl: './auth-page.scss',
})
export class AuthPage {
  private readonly fb = inject(FormBuilder);
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly lang = inject(LanguageService);
  readonly theme = inject(ThemeService);

  readonly isLoading = signal(false);
  // Flips on only if a login request is still in flight after a few
  // seconds — distinguishes a normal brief wait from one long enough that
  // the user might otherwise assume the click didn't register and try
  // again (e.g. a cold-started backend on Render taking 10-60s to wake up).
  readonly isSlow = signal(false);
  private slowTimer: ReturnType<typeof setTimeout> | null = null;
  private static readonly SLOW_THRESHOLD_MS = 4000;

  readonly errorMessage = signal<string | null>(
    this.authService.consumeSessionExpired() ? this.lang.translate('auth.sessionExpired') : null,
  );

  readonly signinForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required]],
  });

  toggleLanguage(): void {
    this.lang.toggle();
  }

  toggleTheme(): void {
    this.theme.toggle();
  }

  submitSignin(): void {
    if (this.signinForm.invalid || this.isLoading()) {
      this.signinForm.markAllAsTouched();
      return;
    }

    this.isLoading.set(true);
    this.isSlow.set(false);
    this.errorMessage.set(null);
    this.slowTimer = setTimeout(() => this.isSlow.set(true), AuthPage.SLOW_THRESHOLD_MS);

    this.authService.login(this.signinForm.getRawValue()).subscribe({
      next: () => this.redirectAfterAuth(),
      error: (err: HttpErrorResponse) => this.handleError(err),
    });
  }

  private clearSlowTimer(): void {
    if (this.slowTimer !== null) {
      clearTimeout(this.slowTimer);
      this.slowTimer = null;
    }
    this.isSlow.set(false);
  }

  private redirectAfterAuth(): void {
    this.isLoading.set(false);
    this.clearSlowTimer();

    // Set by auth.interceptor.ts when a 401 forced this login (session
    // expiry mid-session) — send the user back where they were instead of
    // the role-based default below. Role-specific route guards still apply
    // as normal once we navigate there, same as any other navigation.
    const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');
    if (returnUrl) {
      this.router.navigateByUrl(returnUrl);
      return;
    }

    if (this.authService.isSuperadmin()) {
      this.router.navigate(['/superadmin']);
    } else if (this.authService.isAdmin()) {
      this.router.navigate(['/dashboard']);
    } else {
      this.router.navigate(['/chat']);
    }
  }

  private handleError(err: HttpErrorResponse): void {
    this.isLoading.set(false);
    this.clearSlowTimer();
    const detail = err.error?.detail;
    this.errorMessage.set(
      typeof detail === 'string' ? detail : this.lang.translate('common.somethingWrong'),
    );
  }
}
