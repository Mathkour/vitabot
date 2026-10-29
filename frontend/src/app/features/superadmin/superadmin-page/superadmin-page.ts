import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { AdminSessionService } from '../../../core/services/admin-session.service';
import { LanguageService } from '../../../core/services/language.service';
import { SuperadminService } from '../../../core/services/superadmin.service';
import { SuperadminTenant } from '../../../core/models/superadmin.models';
import { PasswordToggleDirective } from '../../../shared/directives/password-toggle.directive';
import { SuperadminNav } from '../superadmin-nav/superadmin-nav';

@Component({
  selector: 'app-superadmin-page',
  imports: [ReactiveFormsModule, SuperadminNav, PasswordToggleDirective],
  templateUrl: './superadmin-page.html',
  styleUrl: './superadmin-page.scss',
})
export class SuperadminPage implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly superadminService = inject(SuperadminService);
  private readonly adminSession = inject(AdminSessionService);
  readonly lang = inject(LanguageService);

  readonly tenants = signal<SuperadminTenant[]>([]);
  readonly isLoading = signal(false);
  readonly loadError = signal<string | null>(null);

  readonly isModalOpen = signal(false);
  readonly isCreating = signal(false);
  readonly createError = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    company_name: ['', [Validators.required, Validators.minLength(2)]],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
  });

  ngOnInit(): void {
    this.loadTenants();
  }

  openModal(): void {
    this.form.reset({ company_name: '', email: '', password: '' });
    this.createError.set(null);
    this.isModalOpen.set(true);
  }

  closeModal(): void {
    if (this.isCreating()) return;
    this.isModalOpen.set(false);
  }

  submit(): void {
    if (this.form.invalid || this.isCreating()) {
      this.form.markAllAsTouched();
      return;
    }

    this.isCreating.set(true);
    this.createError.set(null);

    this.superadminService.createTenant(this.form.getRawValue()).subscribe({
      next: () => {
        this.isCreating.set(false);
        this.isModalOpen.set(false);
        this.successMessage.set(this.lang.translate('superadmin.createdSuccess'));
        this.loadTenants();
      },
      error: (err: HttpErrorResponse) => {
        this.isCreating.set(false);
        if (err.status === 409) {
          this.createError.set(this.lang.translate('superadmin.emailAlreadyRegistered'));
        } else {
          const detail = err.error?.detail;
          this.createError.set(
            typeof detail === 'string' ? detail : this.lang.translate('superadmin.couldNotCreateCompany'),
          );
        }
      },
    });
  }

  enterAsTenant(tenant: SuperadminTenant): void {
    this.adminSession.enterTenant(tenant);
  }

  formatDate(value: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  }

  private loadTenants(): void {
    this.isLoading.set(true);
    this.loadError.set(null);

    this.superadminService.listTenants().subscribe({
      next: (tenants) => {
        this.tenants.set(tenants);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.loadError.set(
          typeof detail === 'string' ? detail : this.lang.translate('superadmin.couldNotLoadTenants'),
        );
        this.isLoading.set(false);
      },
    });
  }
}
