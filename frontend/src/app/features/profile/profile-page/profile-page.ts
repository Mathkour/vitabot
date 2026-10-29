import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { COUNTRIES, flagUrl } from '../../../core/constants/countries';
import { AuthService } from '../../../core/services/auth.service';
import { LanguageService } from '../../../core/services/language.service';

@Component({
  selector: 'app-profile-page',
  imports: [FormsModule],
  templateUrl: './profile-page.html',
  styleUrl: './profile-page.scss',
})
export class ProfilePage {
  readonly auth = inject(AuthService);
  readonly lang = inject(LanguageService);
  private readonly router = inject(Router);

  readonly countries = COUNTRIES;
  readonly flagUrl = flagUrl;

  readonly usernameDraft = signal(this.auth.currentUser().username ?? '');
  readonly isSaving = signal(false);
  readonly successMessage = signal<string | null>(null);
  readonly errorMessage = signal<string | null>(null);

  readonly countryCodeDraft = signal(this.auth.currentUser().countryCode ?? COUNTRIES[0].dialCode);
  readonly selectedCountryIso = computed(
    () => this.countries.find((c) => c.dialCode === this.countryCodeDraft())?.iso2 ?? this.countries[0].iso2,
  );
  readonly phoneDraft = signal(this.auth.currentUser().phone ?? '');
  readonly isSavingPhone = signal(false);
  readonly phoneSuccessMessage = signal<string | null>(null);
  readonly phoneErrorMessage = signal<string | null>(null);

  get initials(): string {
    const user = this.auth.currentUser();
    const name = user.username || user.email || '';
    return name.charAt(0).toUpperCase() || '?';
  }

  goToChat(): void {
    this.router.navigate(['/chat']);
  }

  saveUsername(): void {
    const username = this.usernameDraft().trim();
    const current = this.auth.currentUser().username ?? '';
    if (!username || username === current || this.isSaving()) return;

    this.isSaving.set(true);
    this.successMessage.set(null);
    this.errorMessage.set(null);

    this.auth.updateUsername(username).subscribe({
      next: () => {
        this.isSaving.set(false);
        this.successMessage.set(this.lang.translate('profile.usernameUpdated'));
      },
      error: (err: HttpErrorResponse) => {
        this.isSaving.set(false);
        if (err.status === 409) {
          this.errorMessage.set(this.lang.translate('profile.usernameTaken'));
        } else {
          const detail = err.error?.detail;
          this.errorMessage.set(
            typeof detail === 'string' ? detail : this.lang.translate('profile.usernameError'),
          );
        }
      },
    });
  }

  savePhone(): void {
    const phone = this.phoneDraft().trim();
    const countryCode = this.countryCodeDraft();
    if (!phone || this.isSavingPhone()) return;

    this.isSavingPhone.set(true);
    this.phoneSuccessMessage.set(null);
    this.phoneErrorMessage.set(null);

    this.auth.updatePhone(phone, countryCode).subscribe({
      next: () => {
        this.isSavingPhone.set(false);
        this.phoneSuccessMessage.set(this.lang.translate('profile.phoneUpdated'));
      },
      error: (err: HttpErrorResponse) => {
        this.isSavingPhone.set(false);
        const detail = err.error?.detail;
        this.phoneErrorMessage.set(
          typeof detail === 'string' ? detail : this.lang.translate('profile.phoneError'),
        );
      },
    });
  }
}
