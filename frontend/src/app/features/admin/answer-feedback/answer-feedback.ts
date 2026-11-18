import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AnswerFeedbackItem, FeedbackStatus } from '../../../core/models/admin-overview.models';
import { Category } from '../../../core/models/category.models';
import { AdminOverviewService } from '../../../core/services/admin-overview.service';
import { CategoriesService } from '../../../core/services/categories.service';
import { ConfirmDialogService } from '../../../core/services/confirm-dialog.service';
import { LanguageService } from '../../../core/services/language.service';
import { DropdownOption, DropdownSelect } from '../../../shared/dropdown-select/dropdown-select';
import { Pagination } from '../../../shared/pagination/pagination';

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 350;
const ALL_CATEGORIES = '';

/**
 * Answers users rated 👎, with the question, who asked and their comment.
 * "Fix" teaches the bot the right answer (the same knowledge mechanism as
 * Unanswered Questions); "Dismiss" marks the answer as fine.
 */
@Component({
  selector: 'app-answer-feedback',
  imports: [FormsModule, DatePipe, RouterLink, DropdownSelect, Pagination],
  templateUrl: './answer-feedback.html',
  // Same list layout as Unanswered Questions.
  styleUrls: ['../unanswered-questions/unanswered-questions.scss', './answer-feedback.scss'],
})
export class AnswerFeedback implements OnInit, OnDestroy {
  private readonly service = inject(AdminOverviewService);
  private readonly categoriesService = inject(CategoriesService);
  private readonly confirmDialog = inject(ConfirmDialogService);
  readonly lang = inject(LanguageService);

  readonly tabs: { status: FeedbackStatus; icon: string }[] = [
    { status: 'open', icon: 'thumb_down' },
    { status: 'fixed', icon: 'school' },
    { status: 'dismissed', icon: 'block' },
  ];
  readonly activeTab = signal<FeedbackStatus>('open');
  readonly items = signal<AnswerFeedbackItem[]>([]);
  readonly counts = signal<Record<FeedbackStatus, number>>({ open: 0, fixed: 0, dismissed: 0 });
  readonly total = signal(0);
  readonly page = signal(1);
  readonly search = signal('');
  readonly isLoading = signal(true);
  readonly loadError = signal<string | null>(null);

  readonly editingId = signal<string | null>(null);
  readonly draftAnswer = signal('');
  readonly draftCategoryId = signal(ALL_CATEGORIES);
  readonly busyId = signal<string | null>(null);
  readonly rowError = signal<string | null>(null);
  readonly notice = signal<string | null>(null);

  private readonly categories = signal<Category[]>([]);
  readonly categoryOptions = computed<DropdownOption[]>(() => [
    { value: ALL_CATEGORIES, label: this.lang.translate('unanswered.allCategories') },
    ...this.categories().map((c) => ({ value: c.id, label: c.name })),
  ]);
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / PAGE_SIZE)));
  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  ngOnInit(): void {
    this.categoriesService.list().subscribe({ next: (c) => this.categories.set(c), error: () => {} });
    this.load();
  }

  ngOnDestroy(): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
  }

  setActiveTab(tab: FeedbackStatus): void {
    this.activeTab.set(tab);
    this.page.set(1);
    this.closeEditor();
    this.load();
  }

  onSearchChange(value: string): void {
    this.search.set(value);
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.page.set(1);
      this.load();
    }, SEARCH_DEBOUNCE_MS);
  }

  onPageChange(page: number): void {
    this.page.set(page);
    this.closeEditor();
    this.load();
  }

  userLabel(item: AnswerFeedbackItem): string {
    return item.username || item.email || this.lang.translate('unanswered.unknownUser');
  }

  startFixing(item: AnswerFeedbackItem): void {
    this.editingId.set(item.id);
    this.draftAnswer.set(item.corrected_answer ?? '');
    this.draftCategoryId.set(ALL_CATEGORIES);
    this.rowError.set(null);
  }

  closeEditor(): void {
    this.editingId.set(null);
    this.rowError.set(null);
  }

  saveFix(item: AnswerFeedbackItem): void {
    const answer = this.draftAnswer().trim();
    if (!answer || this.busyId()) return;
    this.busyId.set(item.id);
    this.rowError.set(null);
    this.service.fixFeedback(item.id, answer, this.draftCategoryId() || null).subscribe({
      next: () => {
        this.busyId.set(null);
        this.closeEditor();
        this.notice.set(this.lang.translate('feedback.fixed'));
        this.load();
      },
      error: (err: HttpErrorResponse) => this.fail(err, 'unanswered.couldNotSave'),
    });
  }

  dismiss(item: AnswerFeedbackItem): void {
    this.run(item, () => this.service.dismissFeedback(item.id));
  }

  reopen(item: AnswerFeedbackItem): void {
    this.run(item, () => this.service.reopenFeedback(item.id));
  }

  async remove(item: AnswerFeedbackItem): Promise<void> {
    if (this.busyId()) return;
    const confirmed = await this.confirmDialog.confirm({
      title: this.lang.translate('feedback.deleteTitle'),
      message: this.lang.translate('feedback.deleteMessage'),
      confirmLabel: this.lang.translate('common.delete'),
      cancelLabel: this.lang.translate('common.cancel'),
    });
    if (!confirmed) return;
    this.run(item, () => this.service.deleteFeedback(item.id));
  }

  private run(item: AnswerFeedbackItem, call: () => ReturnType<AdminOverviewService['dismissFeedback']>): void {
    if (this.busyId()) return;
    this.busyId.set(item.id);
    this.rowError.set(null);
    this.notice.set(null);
    call().subscribe({
      next: () => {
        this.busyId.set(null);
        this.load();
      },
      error: (err: HttpErrorResponse) => this.fail(err, 'unanswered.couldNotUpdate'),
    });
  }

  private fail(err: HttpErrorResponse, fallbackKey: string): void {
    this.busyId.set(null);
    const detail = err.error?.detail;
    this.rowError.set(typeof detail === 'string' ? detail : this.lang.translate(fallbackKey));
  }

  private load(): void {
    this.isLoading.set(true);
    this.loadError.set(null);
    this.service.feedback(this.activeTab(), this.page(), PAGE_SIZE, this.search()).subscribe({
      next: (res) => {
        this.items.set(res.items);
        this.total.set(res.total);
        this.counts.set(res.counts);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading.set(false);
        const detail = err.error?.detail;
        this.loadError.set(typeof detail === 'string' ? detail : this.lang.translate('feedback.couldNotLoad'));
      },
    });
  }
}
