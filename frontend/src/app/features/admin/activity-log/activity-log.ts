import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivityLogEntry } from '../../../core/models/admin-overview.models';
import { AdminOverviewService } from '../../../core/services/admin-overview.service';
import { LanguageService } from '../../../core/services/language.service';
import { DropdownOption, DropdownSelect } from '../../../shared/dropdown-select/dropdown-select';
import { Pagination } from '../../../shared/pagination/pagination';

const PAGE_SIZE = 30;
const SEARCH_DEBOUNCE_MS = 350;
const AREAS = ['document', 'category', 'media', 'faq', 'error_solution', 'question', 'feedback', 'user', 'company', 'ticket'];
const AREA_ICONS: Record<string, string> = {
  document: 'description', category: 'folder', media: 'perm_media', faq: 'help_center', error_solution: 'build',
  question: 'contact_support', feedback: 'thumb_down', user: 'person', company: 'domain', ticket: 'confirmation_number',
};

/** Who changed what in the admin area, newest first. */
@Component({
  selector: 'app-activity-log',
  imports: [FormsModule, DatePipe, DropdownSelect, Pagination],
  templateUrl: './activity-log.html',
  styleUrl: './activity-log.scss',
})
export class ActivityLog implements OnInit, OnDestroy {
  private readonly service = inject(AdminOverviewService);
  readonly lang = inject(LanguageService);

  readonly items = signal<ActivityLogEntry[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly search = signal('');
  readonly area = signal('');
  readonly isLoading = signal(true);
  readonly loadError = signal<string | null>(null);
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / PAGE_SIZE)));
  readonly areaOptions = computed<DropdownOption[]>(() => [
    { value: '', label: this.lang.translate('activity.allAreas') },
    ...AREAS.map((a) => ({ value: a, label: this.lang.translate('activity.area.' + a) })),
  ]);
  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  ngOnInit(): void {
    this.load();
  }

  ngOnDestroy(): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
  }

  icon(action: string): string {
    return AREA_ICONS[action.split('.')[0]] ?? 'history';
  }

  /** 'faq.update' -> translated "Updated FAQ"; unknown actions fall back to the raw code. */
  actionLabel(action: string): string {
    const key = 'activity.action.' + action;
    const label = this.lang.translate(key);
    return label === key ? action : label;
  }

  onSearchChange(value: string): void {
    this.search.set(value);
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.page.set(1);
      this.load();
    }, SEARCH_DEBOUNCE_MS);
  }

  onAreaChange(value: string): void {
    this.area.set(value);
    this.page.set(1);
    this.load();
  }

  onPageChange(page: number): void {
    this.page.set(page);
    this.load();
  }

  private load(): void {
    this.isLoading.set(true);
    this.loadError.set(null);
    this.service.activityLog(this.page(), PAGE_SIZE, this.search(), this.area()).subscribe({
      next: (res) => {
        this.items.set(res.items);
        this.total.set(res.total);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading.set(false);
        const detail = err.error?.detail;
        this.loadError.set(typeof detail === 'string' ? detail : this.lang.translate('activity.couldNotLoad'));
      },
    });
  }
}
