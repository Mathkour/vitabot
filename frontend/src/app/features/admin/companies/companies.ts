import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Company, CompanyOdooRequest } from '../../../core/models/company.models';
import { CompanyService } from '../../../core/services/company.service';
import { ConfirmDialogService } from '../../../core/services/confirm-dialog.service';
import { LanguageService } from '../../../core/services/language.service';
import { PasswordToggleDirective } from '../../../shared/directives/password-toggle.directive';

@Component({
  selector: 'app-companies',
  imports: [FormsModule, PasswordToggleDirective],
  templateUrl: './companies.html',
  styleUrl: './companies.scss',
})
export class Companies implements OnInit {
  private readonly companyService = inject(CompanyService);
  private readonly confirmDialog = inject(ConfirmDialogService);
  readonly lang = inject(LanguageService);

  readonly companies = signal<Company[]>([]);
  readonly isLoading = signal(false);
  readonly loadError = signal<string | null>(null);

  readonly newCompanyName = signal('');
  readonly isCreating = signal(false);
  readonly createError = signal<string | null>(null);

  readonly editingId = signal<string | null>(null);
  readonly editingName = signal('');

  // Ask Odoo settings dialog
  readonly odooCompany = signal<Company | null>(null);
  readonly odooLoading = signal(false);
  readonly odooSaving = signal(false);
  readonly odooTesting = signal(false);
  readonly odooError = signal<string | null>(null);
  readonly odooTestResult = signal<{ ok: boolean; message: string } | null>(null);
  readonly odooHasPassword = signal(false);
  readonly odooEnabled = signal(false);
  readonly odooUrl = signal('');
  readonly odooDb = signal('');
  readonly odooUsername = signal('');
  readonly odooPassword = signal('');

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.isLoading.set(true);
    this.loadError.set(null);
    this.companyService.list().subscribe({
      next: (companies) => {
        this.companies.set(companies);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loadError.set(this.extractError(err, 'companies.couldNotLoad'));
        this.isLoading.set(false);
      },
    });
  }

  createCompany(): void {
    const name = this.newCompanyName().trim();
    if (!name || this.isCreating()) return;

    this.isCreating.set(true);
    this.createError.set(null);
    this.companyService.create({ name }).subscribe({
      next: () => {
        this.newCompanyName.set('');
        this.isCreating.set(false);
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.createError.set(this.extractError(err, 'companies.couldNotCreate'));
        this.isCreating.set(false);
      },
    });
  }

  startEdit(company: Company): void {
    this.editingId.set(company.id);
    this.editingName.set(company.name);
  }

  cancelEdit(): void {
    this.editingId.set(null);
    this.editingName.set('');
  }

  saveEdit(company: Company): void {
    const name = this.editingName().trim();
    if (!name) return;
    this.companyService.rename(company.id, { name }).subscribe({
      next: () => {
        this.cancelEdit();
        this.load();
      },
      error: () => this.cancelEdit(),
    });
  }

  async deleteCompany(company: Company): Promise<void> {
    const confirmed = await this.confirmDialog.confirm({
      title: this.lang.translate('companies.deleteTitle'),
      message: this.lang.translate('companies.deleteMessage').replace('{name}', company.name),
      confirmLabel: this.lang.translate('common.delete'),
      cancelLabel: this.lang.translate('common.cancel'),
    });
    if (!confirmed) return;

    this.companyService.delete(company.id).subscribe({
      next: () => this.load(),
    });
  }

  // ──────────── Ask Odoo per company ────────────

  openOdoo(company: Company): void {
    this.odooCompany.set(company);
    this.odooError.set(null);
    this.odooTestResult.set(null);
    this.odooPassword.set('');
    this.odooLoading.set(true);
    this.companyService.getOdoo(company.id).subscribe({
      next: (s) => {
        this.odooEnabled.set(s.enabled);
        this.odooUrl.set(s.url);
        this.odooDb.set(s.db);
        this.odooUsername.set(s.username);
        this.odooHasPassword.set(s.has_password);
        this.odooLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.odooError.set(this.extractError(err, 'companies.odooCouldNotLoad'));
        this.odooLoading.set(false);
      },
    });
  }

  closeOdoo(): void {
    if (this.odooSaving()) return;
    this.odooCompany.set(null);
    this.odooPassword.set('');
  }

  private odooPayload(): CompanyOdooRequest {
    return {
      enabled: this.odooEnabled(),
      url: this.odooUrl().trim(),
      db: this.odooDb().trim(),
      username: this.odooUsername().trim(),
      password: this.odooPassword() || null,
    };
  }

  testOdoo(): void {
    const company = this.odooCompany();
    if (!company || this.odooTesting()) return;
    this.odooTesting.set(true);
    this.odooTestResult.set(null);
    this.odooError.set(null);
    this.companyService.testOdoo(company.id, this.odooPayload()).subscribe({
      next: (r) => {
        this.odooTestResult.set({
          ok: r.ok,
          message: r.ok ? this.lang.translate('companies.odooTestOk') : (r.error ?? ''),
        });
        this.odooTesting.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.odooTestResult.set({ ok: false, message: this.extractError(err, 'companies.odooTestFailed') });
        this.odooTesting.set(false);
      },
    });
  }

  saveOdoo(): void {
    const company = this.odooCompany();
    if (!company || this.odooSaving()) return;
    this.odooSaving.set(true);
    this.odooError.set(null);
    this.companyService.saveOdoo(company.id, this.odooPayload()).subscribe({
      next: () => {
        this.odooSaving.set(false);
        this.closeOdoo();
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.odooError.set(this.extractError(err, 'companies.odooCouldNotSave'));
        this.odooSaving.set(false);
      },
    });
  }

  private extractError(err: HttpErrorResponse, fallbackKey: string): string {
    const detail = err.error?.detail;
    return typeof detail === 'string' ? detail : this.lang.translate(fallbackKey);
  }
}
