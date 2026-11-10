import { HttpErrorResponse } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ConversationSearchHit } from '../../../core/models/admin-overview.models';
import { Company } from '../../../core/models/company.models';
import { CompanyUser } from '../../../core/models/user.models';
import { AdminOverviewService } from '../../../core/services/admin-overview.service';
import { CompanyService } from '../../../core/services/company.service';
import { LanguageService } from '../../../core/services/language.service';
import { UsersService } from '../../../core/services/users.service';
import { DropdownOption, DropdownSelect } from '../../../shared/dropdown-select/dropdown-select';
import { Pagination } from '../../../shared/pagination/pagination';

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;
const MESSAGE_PAGE_SIZE = 20;

@Component({
  selector: 'app-conversations',
  imports: [FormsModule, Pagination, DatePipe, DropdownSelect],
  templateUrl: './conversations.html',
  styleUrl: './conversations.scss',
})
export class Conversations implements OnInit {
  private readonly usersService = inject(UsersService);
  private readonly router = inject(Router);
  readonly lang = inject(LanguageService);
  private searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  readonly users = signal<CompanyUser[]>([]);
  readonly usersLoading = signal(false);
  readonly usersError = signal<string | null>(null);

  readonly searchTerm = signal('');
  readonly page = signal(1);
  readonly total = signal(0);
  readonly totalPages = signal(1);

  /** 'users' = pick a user and read their chats; 'messages' = search every chat. */
  readonly mode = signal<'users' | 'messages'>('users');

  private readonly overview = inject(AdminOverviewService);
  private readonly companyService = inject(CompanyService);
  private readonly companies = signal<Company[]>([]);
  readonly companyOptions = computed<DropdownOption[]>(() => [
    { value: '', label: this.lang.translate('users.allCompanies') },
    { value: 'none', label: this.lang.translate('users.noCompany') },
    ...this.companies().map((c) => ({ value: c.id, label: c.name })),
  ]);
  readonly msgQuery = signal('');
  readonly msgFrom = signal('');
  readonly msgTo = signal('');
  readonly msgCompany = signal('');
  readonly msgOnlyDisliked = signal(false);
  readonly msgPage = signal(1);
  readonly msgTotal = signal(0);
  readonly msgHits = signal<ConversationSearchHit[]>([]);
  readonly msgLoading = signal(false);
  readonly msgError = signal<string | null>(null);
  readonly msgSearched = signal(false);
  readonly msgTotalPages = computed(() => Math.max(1, Math.ceil(this.msgTotal() / MESSAGE_PAGE_SIZE)));
  private msgDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  ngOnInit(): void {
    this.loadUsers();
    // Companies are Vita Care only; elsewhere the filter just lists "All / No company".
    this.companyService.list().subscribe({ next: (c) => this.companies.set(c), error: () => {} });
  }

  setMode(mode: 'users' | 'messages'): void {
    this.mode.set(mode);
    if (mode === 'messages' && !this.msgSearched()) this.searchMessages();
  }

  /** Re-runs the message search; typing is debounced, other filters apply at once. */
  onMessageFilterChange(debounce = false): void {
    if (this.msgDebounceTimer) clearTimeout(this.msgDebounceTimer);
    const run = () => {
      this.msgPage.set(1);
      this.searchMessages();
    };
    if (debounce) this.msgDebounceTimer = setTimeout(run, SEARCH_DEBOUNCE_MS);
    else run();
  }

  clearMessageFilters(): void {
    this.msgQuery.set('');
    this.msgFrom.set('');
    this.msgTo.set('');
    this.msgCompany.set('');
    this.msgOnlyDisliked.set(false);
    this.onMessageFilterChange();
  }

  goToMessagePage(page: number): void {
    this.msgPage.set(page);
    this.searchMessages();
  }

  openHit(hit: ConversationSearchHit): void {
    if (hit.user_id) this.router.navigate(['/conversations', hit.user_id]);
  }

  private searchMessages(): void {
    this.msgLoading.set(true);
    this.msgError.set(null);
    this.msgSearched.set(true);
    this.overview
      .searchConversations(
        {
          q: this.msgQuery(),
          dateFrom: this.msgFrom() || undefined,
          dateTo: this.msgTo() || undefined,
          companyId: this.msgCompany() || undefined,
          onlyDisliked: this.msgOnlyDisliked(),
          page: this.msgPage(),
        },
        MESSAGE_PAGE_SIZE,
      )
      .subscribe({
        next: (res) => {
          this.msgHits.set(res.items);
          this.msgTotal.set(res.total);
          this.msgLoading.set(false);
        },
        error: (err: HttpErrorResponse) => {
          const detail = err.error?.detail;
          this.msgError.set(typeof detail === 'string' ? detail : this.lang.translate('conversations.searchFailed'));
          this.msgLoading.set(false);
        },
      });
  }

  onSearchChange(value: string): void {
    this.searchTerm.set(value);
    if (this.searchDebounceTimer) clearTimeout(this.searchDebounceTimer);
    this.searchDebounceTimer = setTimeout(() => {
      this.page.set(1);
      this.loadUsers();
    }, SEARCH_DEBOUNCE_MS);
  }

  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages() || page === this.page()) return;
    this.page.set(page);
    this.loadUsers();
  }

  openConversations(user: CompanyUser): void {
    this.router.navigate(['/conversations', user.id]);
  }

  roleBadgeClass(role: string): string {
    return role === 'admin' ? 'pill-info' : 'pill-success';
  }

  private loadUsers(): void {
    this.usersLoading.set(true);
    this.usersError.set(null);

    this.usersService
      .list({
        search: this.searchTerm().trim() || undefined,
        page: this.page(),
        page_size: PAGE_SIZE,
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
          this.usersError.set(
            typeof detail === 'string' ? detail : this.lang.translate('conversations.couldNotLoadUsers'),
          );
          this.usersLoading.set(false);
        },
      });
  }
}
