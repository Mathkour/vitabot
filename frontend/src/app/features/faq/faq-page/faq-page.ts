import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import Fuse from 'fuse.js';
import { FaqCategorySummary, FaqItem } from '../../../core/models/faq.models';
import { FaqService } from '../../../core/services/faq.service';
import { LanguageService } from '../../../core/services/language.service';
import { Pagination } from '../../../shared/pagination/pagination';

const LIST_PAGE_SIZE = 10;

const FUSE_OPTIONS: ConstructorParameters<typeof Fuse<FaqItem>>[1] = {
  keys: ['question'],
  threshold: 0.35,
  ignoreLocation: true,
  useExtendedSearch: false,
};

/** Per-category accordion state, populated lazily the first time that
 * category is opened (and re-fetched on page change within it). */
interface CategoryPageState {
  faqs: FaqItem[];
  page: number;
  totalPages: number;
  total: number;
  loading: boolean;
  error: string | null;
}

@Component({
  selector: 'app-faq-page',
  imports: [FormsModule, Pagination],
  templateUrl: './faq-page.html',
  styleUrl: './faq-page.scss',
})
export class FaqPage implements OnInit {
  private readonly faqService = inject(FaqService);
  readonly lang = inject(LanguageService);

  /** Accordion headers — name + total count per category, no FAQ text. */
  readonly categorySummaries = signal<FaqCategorySummary[]>([]);
  readonly expandedCategoryIds = signal<Set<string>>(new Set());
  /** Lazily populated as each category is opened. */
  readonly categoryPages = signal<Map<string, CategoryPageState>>(new Map());

  readonly isLoading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly expandedIds = signal<Set<string>>(new Set());

  readonly searchQuery = signal('');
  readonly isSearching = computed(() => this.searchQuery().trim().length > 0);

  /** Full flat corpus for client-side fuzzy search — null until the member
   * actually searches, so a visit that never searches never fetches it. */
  readonly searchCorpusItems = signal<FaqItem[] | null>(null);
  readonly searchCorpusLoading = signal(false);
  readonly searchCorpusError = signal<string | null>(null);

  private readonly fuse = computed(() => new Fuse(this.searchCorpusItems() ?? [], FUSE_OPTIONS));

  readonly filteredItems = computed(() => {
    const query = this.searchQuery().trim();
    const corpus = this.searchCorpusItems() ?? [];
    if (!query) return corpus;
    return this.fuse()
      .search(query)
      .map((result) => result.item);
  });

  readonly page = signal(1);
  readonly totalPages = computed(() =>
    Math.max(1, Math.ceil(this.filteredItems().length / LIST_PAGE_SIZE)),
  );
  readonly pagedItems = computed(() => {
    const start = (this.page() - 1) * LIST_PAGE_SIZE;
    return this.filteredItems().slice(start, start + LIST_PAGE_SIZE);
  });

  ngOnInit(): void {
    this.faqService.listGroupedSummary().subscribe({
      next: (summaries) => {
        this.categorySummaries.set(summaries);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading.set(false);
        const detail = err.error?.detail;
        this.errorMessage.set(typeof detail === 'string' ? detail : this.lang.translate('faq.couldNotLoad'));
      },
    });
  }

  onSearchChange(value: string): void {
    this.searchQuery.set(value);
    this.page.set(1);
    if (value.trim() && this.searchCorpusItems() === null && !this.searchCorpusLoading()) {
      this.loadSearchCorpus();
    }
  }

  toggle(id: string): void {
    this.expandedIds.update((s) => {
      const n = new Set(s);
      if (n.has(id)) {
        n.delete(id);
      } else {
        n.add(id);
      }
      return n;
    });
  }

  toggleCategory(categoryId: string): void {
    const wasOpen = this.expandedCategoryIds().has(categoryId);
    this.expandedCategoryIds.update((s) => {
      const n = new Set(s);
      if (wasOpen) {
        n.delete(categoryId);
      } else {
        n.add(categoryId);
      }
      return n;
    });
    if (!wasOpen && !this.categoryPages().has(categoryId)) {
      this.loadCategoryPage(categoryId, 1);
    }
  }

  goToCategoryPage(categoryId: string, page: number): void {
    this.loadCategoryPage(categoryId, page);
  }

  categoryPageState(categoryId: string): CategoryPageState | undefined {
    return this.categoryPages().get(categoryId);
  }

  categoryName(summary: FaqCategorySummary): string {
    return this.lang.lang() === 'ar' ? summary.name_ar || summary.name_en : summary.name_en || summary.name_ar;
  }

  // Admin-authored content is translated once at write time (main.py) and
  // cached in question_ar/answer_ar — a null value there (not yet
  // translated, or the translation call failed) falls back to English
  // rather than showing nothing.
  displayQuestion(item: FaqItem): string {
    return this.lang.lang() === 'ar' ? item.question_ar || item.question : item.question;
  }

  displayAnswer(item: FaqItem): string {
    return this.lang.lang() === 'ar' ? item.answer_ar || item.answer : item.answer;
  }

  private loadCategoryPage(categoryId: string, page: number): void {
    this.categoryPages.update((m) => {
      const n = new Map(m);
      const existing = n.get(categoryId);
      n.set(categoryId, {
        faqs: existing?.faqs ?? [],
        page,
        totalPages: existing?.totalPages ?? 1,
        total: existing?.total ?? 0,
        loading: true,
        error: null,
      });
      return n;
    });

    this.faqService.listCategoryPage(categoryId, page, LIST_PAGE_SIZE).subscribe({
      next: (result) => {
        this.categoryPages.update((m) => {
          const n = new Map(m);
          n.set(categoryId, {
            faqs: result.faqs,
            page: result.page,
            totalPages: result.total_pages,
            total: result.total,
            loading: false,
            error: null,
          });
          return n;
        });
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.categoryPages.update((m) => {
          const n = new Map(m);
          const existing = n.get(categoryId);
          n.set(categoryId, {
            faqs: existing?.faqs ?? [],
            page: existing?.page ?? 1,
            totalPages: existing?.totalPages ?? 1,
            total: existing?.total ?? 0,
            loading: false,
            error: typeof detail === 'string' ? detail : this.lang.translate('faq.couldNotLoad'),
          });
          return n;
        });
      },
    });
  }

  private loadSearchCorpus(): void {
    this.searchCorpusLoading.set(true);
    this.searchCorpusError.set(null);

    this.faqService.searchCorpus().subscribe({
      next: (items) => {
        this.searchCorpusItems.set(items);
        this.searchCorpusLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.searchCorpusLoading.set(false);
        const detail = err.error?.detail;
        this.searchCorpusError.set(
          typeof detail === 'string' ? detail : this.lang.translate('faq.couldNotLoad'),
        );
      },
    });
  }
}
