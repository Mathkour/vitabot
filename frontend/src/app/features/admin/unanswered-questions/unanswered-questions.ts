import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Category } from '../../../core/models/category.models';
import { UnansweredQuestion, UnansweredQuestionStatus } from '../../../core/models/unanswered-question.models';
import { CategoriesService } from '../../../core/services/categories.service';
import { ConfirmDialogService } from '../../../core/services/confirm-dialog.service';
import { LanguageService } from '../../../core/services/language.service';
import { UnansweredQuestionsService } from '../../../core/services/unanswered-questions.service';
import { DropdownOption, DropdownSelect } from '../../../shared/dropdown-select/dropdown-select';
import { Pagination } from '../../../shared/pagination/pagination';

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 350;
// DropdownSelect needs a string value; '' means "no category" (applies to all).
const ALL_CATEGORIES = '';

/**
 * Questions the bot answered with "I don't know", with who asked them, so an
 * admin can answer them. An answer becomes knowledge the bot uses from then
 * on (see routers/unanswered_questions.py).
 */
@Component({
  selector: 'app-unanswered-questions',
  imports: [FormsModule, DatePipe, DropdownSelect, Pagination],
  templateUrl: './unanswered-questions.html',
  styleUrl: './unanswered-questions.scss',
})
export class UnansweredQuestions implements OnInit, OnDestroy {
  private readonly service = inject(UnansweredQuestionsService);
  private readonly categoriesService = inject(CategoriesService);
  private readonly confirmDialog = inject(ConfirmDialogService);
  readonly lang = inject(LanguageService);

  readonly tabs: { status: UnansweredQuestionStatus; icon: string }[] = [
    { status: 'open', icon: 'help' },
    { status: 'answered', icon: 'check_circle' },
    { status: 'dismissed', icon: 'block' },
  ];
  readonly activeTab = signal<UnansweredQuestionStatus>('open');
  readonly items = signal<UnansweredQuestion[]>([]);
  readonly counts = signal<Record<UnansweredQuestionStatus, number>>({ open: 0, answered: 0, dismissed: 0 });
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

  setActiveTab(tab: UnansweredQuestionStatus): void {
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

  userLabel(item: UnansweredQuestion): string {
    return item.username || item.email || this.lang.translate('unanswered.unknownUser');
  }

  startEditing(item: UnansweredQuestion): void {
    this.editingId.set(item.id);
    this.draftAnswer.set(item.answer ?? '');
    this.draftCategoryId.set(item.category_id ?? ALL_CATEGORIES);
    this.rowError.set(null);
  }

  closeEditor(): void {
    this.editingId.set(null);
    this.rowError.set(null);
  }

  saveAnswer(item: UnansweredQuestion): void {
    const answer = this.draftAnswer().trim();
    if (!answer || this.busyId()) return;
    this.busyId.set(item.id);
    this.rowError.set(null);
    this.service.answer(item.id, answer, this.draftCategoryId() || null).subscribe({
      next: (res) => {
        this.busyId.set(null);
        this.closeEditor();
        this.notice.set(
          res.updated > 1
            ? this.lang.translate('unanswered.savedMany').replace('{n}', String(res.updated))
            : this.lang.translate('unanswered.saved'),
        );
        this.load();
      },
      error: (err: HttpErrorResponse) => this.fail(err, 'unanswered.couldNotSave'),
    });
  }

  async removeAnswer(item: UnansweredQuestion): Promise<void> {
    if (this.busyId()) return;
    const confirmed = await this.confirmDialog.confirm({
      title: this.lang.translate('unanswered.removeTitle'),
      message: this.lang.translate('unanswered.confirmRemove'),
      confirmLabel: this.lang.translate('unanswered.removeAnswer'),
      cancelLabel: this.lang.translate('common.cancel'),
    });
    if (!confirmed) return;
    this.runAction(item, this.service.removeAnswer(item.id));
  }

  dismiss(item: UnansweredQuestion): void {
    this.runAction(item, this.service.dismiss(item.id));
  }

  reopen(item: UnansweredQuestion): void {
    this.runAction(item, this.service.reopen(item.id));
  }

  private runAction(item: UnansweredQuestion, request: ReturnType<UnansweredQuestionsService['dismiss']>): void {
    if (this.busyId()) return;
    this.busyId.set(item.id);
    this.rowError.set(null);
    this.notice.set(null);
    request.subscribe({
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
    this.service.list(this.activeTab(), this.page(), PAGE_SIZE, this.search()).subscribe({
      next: (res) => {
        this.items.set(res.items);
        this.total.set(res.total);
        this.counts.set(res.counts);
        this.service.openCountValue.set(res.counts.open);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading.set(false);
        const detail = err.error?.detail;
        this.loadError.set(typeof detail === 'string' ? detail : this.lang.translate('unanswered.couldNotLoad'));
      },
    });
  }
}
