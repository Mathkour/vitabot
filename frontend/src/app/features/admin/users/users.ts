import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import * as XLSX from 'xlsx';
import { Company } from '../../../core/models/company.models';
import { CompanyUser, ImportPreviewResponse } from '../../../core/models/user.models';
import { AuthService } from '../../../core/services/auth.service';
import { CompanyService } from '../../../core/services/company.service';
import { ConfirmDialogService } from '../../../core/services/confirm-dialog.service';
import { LanguageService } from '../../../core/services/language.service';
import { UsersService } from '../../../core/services/users.service';
import { PasswordToggleDirective } from '../../../shared/directives/password-toggle.directive';
import { DropdownOption, DropdownSelect } from '../../../shared/dropdown-select/dropdown-select';
import { Pagination } from '../../../shared/pagination/pagination';

const PAGE_SIZE = 10;
const SEARCH_DEBOUNCE_MS = 300;

@Component({
  selector: 'app-users',
  imports: [ReactiveFormsModule, FormsModule, Pagination, PasswordToggleDirective, DropdownSelect],
  templateUrl: './users.html',
  styleUrl: './users.scss',
})
export class Users implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly authService = inject(AuthService);
  private readonly usersService = inject(UsersService);
  private readonly companyService = inject(CompanyService);
  private readonly confirmDialog = inject(ConfirmDialogService);
  readonly lang = inject(LanguageService);
  private searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  readonly isCompanyAdmin = computed(() => this.authService.isCompanyAdmin());
  readonly isTenantAdmin = computed(() => this.authService.isAdmin() || this.authService.isSuperadmin());

  /** Only populated for tenants where the companies feature is actually
   * wired up (GET /companies 403s for every other tenant — see
   * require_vita_care_admin — which is caught silently here, since not
   * having companies is the normal case for most tenants, not an error). */
  readonly companies = signal<Company[]>([]);
  readonly companyFilter = signal<string>('');

  /** "No company" + every real company, for the inline per-row assignment
   * dropdown (app-dropdown-select) — same list shape used for the create-user
   * modal's company picker below. */
  readonly companyDropdownOptions = computed<DropdownOption[]>(() => [
    { value: '', label: this.lang.translate('users.noCompany') },
    ...this.companies().map((c) => ({ value: c.id, label: c.name })),
  ]);

  readonly isModalOpen = signal(false);
  readonly isLoading = signal(false);
  readonly errorMessage = signal<string | null>(null);

  readonly importResultMessage = signal<string | null>(null);
  readonly isImportModalOpen = signal(false);
  readonly isImportPreviewLoading = signal(false);
  readonly isConfirmingImport = signal(false);
  readonly importPreviewData = signal<ImportPreviewResponse | null>(null);
  readonly importError = signal<string | null>(null);
  private importFile: File | null = null;

  readonly users = signal<CompanyUser[]>([]);
  readonly usersLoading = signal(false);
  readonly usersListError = signal<string | null>(null);

  /** Inline "assign to company" editing, one row at a time — tenant admin
   * only (PATCH /users/{id} 403s for a company_admin trying to change
   * company_id, by design). */
  readonly editingCompanyUserId = signal<string | null>(null);
  readonly editingCompanyId = signal<string>('');
  readonly isSavingCompany = signal(false);

  /** Inline role change, tenant admin only, never on your own row (the
   * backend refuses that too, along with demoting the last admin). */
  readonly editingRoleUserId = signal<string | null>(null);
  readonly editingRole = signal<string>('member');
  readonly isSavingRole = signal(false);
  readonly roleError = signal<string | null>(null);
  readonly roleOptions = computed<DropdownOption[]>(() => [
    { value: 'member', label: this.lang.translate('users.roleMember') },
    { value: 'admin', label: this.lang.translate('users.roleAdmin') },
    { value: 'company_admin', label: this.lang.translate('users.roleCompanyAdmin') },
  ]);
  readonly searchTerm = signal('');
  readonly page = signal(1);
  readonly total = signal(0);
  readonly totalPages = signal(1);

  readonly canConfirmImport = computed(() => {
    const data = this.importPreviewData();
    return !!data && data.mapping.email != null && data.mapping.username != null;
  });

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    username: ['', [Validators.required, Validators.minLength(2)]],
    password: ['', [Validators.required, Validators.minLength(8)]],
    role: ['member', [Validators.required]],
    companyId: [''],
  });

  ngOnInit(): void {
    this.loadUsers();
    // A company_admin's own GET /companies is always a 403 (tenant-admin
    // only — see require_vita_care_admin), so only attempt this for a
    // tenant admin; a silent catch below also covers every non-Vita-Care
    // tenant, where this request 403s too.
    if (this.isTenantAdmin()) {
      this.companyService.list().subscribe({
        next: (companies) => this.companies.set(companies),
        error: () => this.companies.set([]),
      });
    }
  }

  onSearchChange(value: string): void {
    this.searchTerm.set(value);
    if (this.searchDebounceTimer) clearTimeout(this.searchDebounceTimer);
    this.searchDebounceTimer = setTimeout(() => {
      this.page.set(1);
      this.loadUsers();
    }, SEARCH_DEBOUNCE_MS);
  }

  onCompanyFilterChange(companyId: string): void {
    this.companyFilter.set(companyId);
    this.page.set(1);
    this.loadUsers();
  }

  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages() || page === this.page()) return;
    this.page.set(page);
    this.loadUsers();
  }

  roleBadgeClass(role: string): string {
    return role === 'admin' ? 'pill-info' : role === 'company_admin' ? 'pill-warning' : 'pill-success';
  }

  roleLabel(role: string): string {
    const key = { admin: 'users.roleAdmin', company_admin: 'users.roleCompanyAdmin', member: 'users.roleMember' }[role];
    return key ? this.lang.translate(key) : role;
  }

  isSelf(user: CompanyUser): boolean {
    const me = this.authService.currentUser().email;
    return !!me && me.toLowerCase() === user.email.toLowerCase();
  }

  startEditRole(user: CompanyUser): void {
    this.editingRoleUserId.set(user.id);
    this.editingRole.set(user.role);
    this.roleError.set(null);
  }

  cancelEditRole(): void {
    this.editingRoleUserId.set(null);
    this.roleError.set(null);
  }

  saveEditRole(user: CompanyUser): void {
    if (this.isSavingRole()) return;
    const role = this.editingRole();
    if (role === user.role) {
      this.cancelEditRole();
      return;
    }
    this.isSavingRole.set(true);
    this.roleError.set(null);
    this.usersService.update(user.id, { role }).subscribe({
      next: () => {
        this.isSavingRole.set(false);
        this.cancelEditRole();
        this.loadUsers();
      },
      error: (err: HttpErrorResponse) => {
        this.isSavingRole.set(false);
        const detail = err.error?.detail;
        this.roleError.set(typeof detail === 'string' ? detail : this.lang.translate('users.couldNotChangeRole'));
      },
    });
  }

  openModal(): void {
    this.form.reset({ email: '', username: '', password: '', role: 'member', companyId: '' });
    this.errorMessage.set(null);
    this.isModalOpen.set(true);
  }

  closeModal(): void {
    if (this.isLoading()) return;
    this.isModalOpen.set(false);
  }

  submit(): void {
    if (this.form.invalid || this.isLoading()) {
      this.form.markAllAsTouched();
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set(null);

    const { email, username, password, role, companyId } = this.form.getRawValue();

    this.usersService
      .create({ email, username, password, role, company_id: companyId || null })
      .subscribe({
        next: () => {
          this.isLoading.set(false);
          this.isModalOpen.set(false);
          this.loadUsers();
        },
        error: (err: HttpErrorResponse) => {
          this.isLoading.set(false);
          if (err.status === 409) {
            this.errorMessage.set(this.lang.translate('users.emailOrUsernameInUse'));
          } else {
            const detail = err.error?.detail;
            this.errorMessage.set(
              typeof detail === 'string' ? detail : this.lang.translate('common.somethingWrong'),
            );
          }
        },
      });
  }

  async deleteUser(user: CompanyUser): Promise<void> {
    const confirmed = await this.confirmDialog.confirm({
      title: this.lang.translate('users.deleteTitle'),
      message: this.lang.translate('users.deleteMessage').replace('{name}', user.username || user.email),
      confirmLabel: this.lang.translate('common.delete'),
      cancelLabel: this.lang.translate('common.cancel'),
    });
    if (!confirmed) return;

    this.usersService.delete(user.id).subscribe({
      next: () => this.loadUsers(),
    });
  }

  startEditCompany(user: CompanyUser): void {
    this.editingCompanyUserId.set(user.id);
    this.editingCompanyId.set(user.company_id ?? '');
  }

  cancelEditCompany(): void {
    this.editingCompanyUserId.set(null);
    this.editingCompanyId.set('');
  }

  saveEditCompany(user: CompanyUser): void {
    if (this.isSavingCompany()) return;
    const companyId = this.editingCompanyId();

    this.isSavingCompany.set(true);
    this.usersService.update(user.id, { company_id: companyId || null }).subscribe({
      next: () => {
        this.isSavingCompany.set(false);
        this.cancelEditCompany();
        this.loadUsers();
      },
      error: () => {
        this.isSavingCompany.set(false);
      },
    });
  }

  onImportFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = '';
    if (!file) return;

    this.importFile = file;
    this.importError.set(null);
    this.importResultMessage.set(null);
    this.importPreviewData.set(null);
    this.isImportPreviewLoading.set(true);
    this.isImportModalOpen.set(true);

    this.usersService.importPreview(file).subscribe({
      next: (res) => {
        this.importPreviewData.set(res);
        this.isImportPreviewLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.isImportPreviewLoading.set(false);
        const detail = err.error?.detail;
        this.importError.set(
          typeof detail === 'string' ? detail : this.lang.translate('users.couldNotReadExcel'),
        );
      },
    });
  }

  closeImportModal(): void {
    if (this.isConfirmingImport()) return;
    this.isImportModalOpen.set(false);
    this.importFile = null;
    this.importPreviewData.set(null);
    this.importError.set(null);
  }

  mappingLabel(value: number | string | null, headers: string[]): string {
    if (value === null || value === undefined || value === '') return this.lang.translate('users.notFound');
    return typeof value === 'number'
      ? headers[value] ?? `${this.lang.translate('users.column')} ${value}`
      : value;
  }

  async confirmImport(): Promise<void> {
    const file = this.importFile;
    const preview = this.importPreviewData();
    if (!file || !preview || this.isConfirmingImport()) return;

    this.isConfirmingImport.set(true);
    this.importError.set(null);

    let rows: string[][];
    try {
      rows = await this.readAllRows(file);
    } catch {
      this.isConfirmingImport.set(false);
      this.importError.set(this.lang.translate('users.couldNotReadExcelRetry'));
      return;
    }

    this.usersService.importConfirm({ mapping: preview.mapping, rows }).subscribe({
      next: (res) => {
        this.isConfirmingImport.set(false);
        this.isImportModalOpen.set(false);
        this.importFile = null;
        this.importPreviewData.set(null);
        const importedWord = this.lang.translate(
          res.imported === 1 ? 'users.countSingular' : 'users.countPlural',
        );
        this.importResultMessage.set(
          `${res.imported} ${importedWord} ${this.lang.translate('users.imported')}, ` +
            `${res.skipped} ${this.lang.translate('users.skipped')}.`,
        );
        this.page.set(1);
        this.loadUsers();
      },
      error: (err: HttpErrorResponse) => {
        this.isConfirmingImport.set(false);
        const detail = err.error?.detail;
        this.importError.set(
          typeof detail === 'string' ? detail : this.lang.translate('users.importFailed'),
        );
      },
    });
  }

  private loadUsers(): void {
    this.usersLoading.set(true);
    this.usersListError.set(null);

    this.usersService
      .list({
        search: this.searchTerm().trim() || undefined,
        page: this.page(),
        page_size: PAGE_SIZE,
        company_id: this.companyFilter() || undefined,
      })
      .subscribe({
        next: (res) => {
          this.users.set(res.users);
          this.total.set(res.total);
          this.totalPages.set(Math.max(1, res.total_pages));
          this.usersLoading.set(false);
        },
        error: (err: HttpErrorResponse) => {
          const detail = err.error?.detail;
          this.usersListError.set(
            typeof detail === 'string' ? detail : this.lang.translate('users.couldNotLoadUsers'),
          );
          this.usersLoading.set(false);
        },
      });
  }

  private async readAllRows(file: File): Promise<string[][]> {
    const buffer = await file.arrayBuffer();
    const workbook = XLSX.read(buffer, { type: 'array' });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    const allRows: unknown[][] = XLSX.utils.sheet_to_json(sheet, {
      header: 1,
      blankrows: false,
    });
    return allRows
      .slice(1)
      .map((row) => row.map((cell) => (cell === undefined || cell === null ? '' : String(cell))));
  }
}
