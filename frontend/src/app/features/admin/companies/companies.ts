import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Company } from '../../../core/models/company.models';
import { CompanyService } from '../../../core/services/company.service';
import { ConfirmDialogService } from '../../../core/services/confirm-dialog.service';
import { LanguageService } from '../../../core/services/language.service';

@Component({
  selector: 'app-companies',
  imports: [FormsModule],
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

  private extractError(err: HttpErrorResponse, fallbackKey: string): string {
    const detail = err.error?.detail;
    return typeof detail === 'string' ? detail : this.lang.translate(fallbackKey);
  }
}
