import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CompanyUser } from '../../../core/models/user.models';
import { LanguageService } from '../../../core/services/language.service';
import { UsersService } from '../../../core/services/users.service';
import { Pagination } from '../../../shared/pagination/pagination';

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;

@Component({
  selector: 'app-conversations',
  imports: [FormsModule, Pagination],
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

  ngOnInit(): void {
    this.loadUsers();
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
