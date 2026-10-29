import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ErrorSolutionItem } from '../../../core/models/error-solution.models';
import { FaqCategory, FaqItem } from '../../../core/models/faq.models';
import { ConfirmDialogService } from '../../../core/services/confirm-dialog.service';
import { ErrorSolutionsService } from '../../../core/services/error-solutions.service';
import { FaqCategoryService } from '../../../core/services/faq-category.service';
import { FaqService } from '../../../core/services/faq.service';
import { LanguageService } from '../../../core/services/language.service';
import { TenantThemeService } from '../../../core/services/tenant-theme.service';
import { Pagination } from '../../../shared/pagination/pagination';

const PAGE_SIZE = 10;
const VITA_CARE_TENANT_NAME = 'Vita Care';

type FaqAdminTab = 'faq' | 'categories' | 'errorSolutions';

@Component({
  selector: 'app-faq',
  imports: [FormsModule, Pagination],
  templateUrl: './faq.html',
  styleUrl: './faq.scss',
})
export class Faq implements OnInit {
  private readonly faqService = inject(FaqService);
  private readonly faqCategoryService = inject(FaqCategoryService);
  private readonly errorSolutionsService = inject(ErrorSolutionsService);
  private readonly confirmDialog = inject(ConfirmDialogService);
  private readonly tenantTheme = inject(TenantThemeService);
  readonly lang = inject(LanguageService);

  readonly activeTab = signal<FaqAdminTab>('faq');
  readonly showErrorSolutionsTab = computed(
    () => this.tenantTheme.tenantName() === VITA_CARE_TENANT_NAME,
  );

  // ──────────── FAQ ────────────

  readonly items = signal<FaqItem[]>([]);
  readonly isLoading = signal(true);
  readonly loadError = signal<string | null>(null);

  /** When true, `items` holds only GET /admin/faqs?uncategorized=true results. */
  readonly uncategorizedOnly = signal(false);
  readonly uncategorizedCount = computed(
    () => this.items().filter((i) => !i.category_id).length,
  );

  readonly page = signal(1);
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.items().length / PAGE_SIZE)));
  readonly pagedItems = computed(() => {
    const start = (this.page() - 1) * PAGE_SIZE;
    return this.items().slice(start, start + PAGE_SIZE);
  });

  readonly newQuestion = signal('');
  readonly newAnswer = signal('');
  readonly newQuestionAr = signal('');
  readonly newAnswerAr = signal('');
  readonly newCategoryId = signal<string>('');
  readonly isAdding = signal(false);
  readonly addError = signal<string | null>(null);

  readonly editingId = signal<string | null>(null);
  readonly editQuestion = signal('');
  readonly editAnswer = signal('');
  readonly editQuestionAr = signal('');
  readonly editAnswerAr = signal('');
  readonly editCategoryId = signal<string>('');
  readonly isSavingEdit = signal(false);
  readonly editError = signal<string | null>(null);

  readonly deletingIds = signal<Set<string>>(new Set());
  readonly deleteError = signal<string | null>(null);

  // ──────────── FAQ categories ────────────

  readonly categories = signal<FaqCategory[]>([]);
  readonly categoriesLoading = signal(true);
  readonly categoriesLoadError = signal<string | null>(null);
  private readonly categoryById = computed(
    () => new Map(this.categories().map((c) => [c.id, c])),
  );

  readonly newCategoryNameAr = signal('');
  readonly newCategoryNameEn = signal('');
  readonly isAddingCategory = signal(false);
  readonly addCategoryError = signal<string | null>(null);

  readonly editingCategoryId = signal<string | null>(null);
  readonly editCategoryNameAr = signal('');
  readonly editCategoryNameEn = signal('');
  readonly editCategoryDisplayOrder = signal<number | null>(null);
  readonly isSavingCategoryEdit = signal(false);
  readonly editCategoryError = signal<string | null>(null);

  readonly deletingCategoryIds = signal<Set<string>>(new Set());
  readonly deleteCategoryError = signal<string | null>(null);

  // ──────────── Error Solutions (Vita Care only) ────────────

  readonly esItems = signal<ErrorSolutionItem[]>([]);
  readonly esIsLoading = signal(true);
  readonly esLoadError = signal<string | null>(null);

  readonly esPage = signal(1);
  readonly esTotalPages = computed(() => Math.max(1, Math.ceil(this.esItems().length / PAGE_SIZE)));
  readonly esPagedItems = computed(() => {
    const start = (this.esPage() - 1) * PAGE_SIZE;
    return this.esItems().slice(start, start + PAGE_SIZE);
  });

  /** When true, `esItems` holds only GET /admin/error-solutions?uncategorized=true results. */
  readonly esUncategorizedOnly = signal(false);
  readonly esUncategorizedCount = computed(
    () => this.esItems().filter((i) => !i.category_id).length,
  );

  readonly esNewErrorText = signal('');
  readonly esNewSolutionText = signal('');
  readonly esNewCategoryId = signal<string>('');
  readonly esIsAdding = signal(false);
  readonly esAddError = signal<string | null>(null);

  readonly esEditingId = signal<string | null>(null);
  readonly esEditErrorText = signal('');
  readonly esEditSolutionText = signal('');
  readonly esEditCategoryId = signal<string>('');
  readonly esIsSavingEdit = signal(false);
  readonly esEditError = signal<string | null>(null);

  readonly esDeletingIds = signal<Set<string>>(new Set());
  readonly esDeleteError = signal<string | null>(null);

  readonly esImportFile = signal<File | null>(null);
  readonly esIsImporting = signal(false);
  readonly esImportError = signal<string | null>(null);
  readonly esImportResultMessage = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
    this.loadCategories();
    if (this.showErrorSolutionsTab()) {
      this.esLoad();
    }
  }

  setActiveTab(tab: FaqAdminTab): void {
    this.activeTab.set(tab);
  }

  /** Display name for a FAQ's category dropdown/badge — current UI language,
   * falling back to the other language rather than showing nothing. */
  categoryName(categoryId: string | null | undefined): string | null {
    if (!categoryId) return null;
    const category = this.categoryById().get(categoryId);
    if (!category) return null;
    return this.lang.lang() === 'ar'
      ? category.name_ar || category.name_en
      : category.name_en || category.name_ar;
  }

  toggleUncategorizedOnly(): void {
    this.uncategorizedOnly.update((v) => !v);
    this.load();
  }

  // ──────────── FAQ actions ────────────

  addFaq(): void {
    const question = this.newQuestion().trim();
    const answer = this.newAnswer().trim();
    const questionAr = this.newQuestionAr().trim();
    const answerAr = this.newAnswerAr().trim();
    // Each field just needs one language filled in — the backend
    // auto-translates whichever side is left blank.
    if ((!question && !questionAr) || (!answer && !answerAr) || this.isAdding()) return;

    this.isAdding.set(true);
    this.addError.set(null);

    this.faqService.create(question, answer, this.newCategoryId() || null, questionAr, answerAr).subscribe({
      next: () => {
        this.isAdding.set(false);
        this.newQuestion.set('');
        this.newAnswer.set('');
        this.newQuestionAr.set('');
        this.newAnswerAr.set('');
        this.newCategoryId.set('');
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.isAdding.set(false);
        const detail = err.error?.detail;
        this.addError.set(
          typeof detail === 'string' ? detail : this.lang.translate('faqAdmin.couldNotAdd'),
        );
      },
    });
  }

  startEdit(item: FaqItem): void {
    this.editingId.set(item.id);
    this.editQuestion.set(item.question);
    this.editAnswer.set(item.answer);
    this.editQuestionAr.set(item.question_ar ?? '');
    this.editAnswerAr.set(item.answer_ar ?? '');
    this.editCategoryId.set(item.category_id ?? '');
    this.editError.set(null);
  }

  cancelEdit(): void {
    this.editingId.set(null);
    this.editQuestion.set('');
    this.editAnswer.set('');
    this.editQuestionAr.set('');
    this.editAnswerAr.set('');
    this.editCategoryId.set('');
    this.editError.set(null);
  }

  saveEdit(item: FaqItem): void {
    const question = this.editQuestion().trim();
    const answer = this.editAnswer().trim();
    const questionAr = this.editQuestionAr().trim();
    const answerAr = this.editAnswerAr().trim();
    if ((!question && !questionAr) || (!answer && !answerAr) || this.isSavingEdit()) return;

    this.isSavingEdit.set(true);
    this.editError.set(null);

    this.faqService
      .update(item.id, question, answer, this.editCategoryId() || null, questionAr, answerAr)
      .subscribe({
        next: () => {
          this.isSavingEdit.set(false);
          this.editingId.set(null);
          this.editQuestion.set('');
          this.editAnswer.set('');
          this.editQuestionAr.set('');
          this.editAnswerAr.set('');
          this.editCategoryId.set('');
          this.load();
        },
        error: (err: HttpErrorResponse) => {
          this.isSavingEdit.set(false);
          const detail = err.error?.detail;
          this.editError.set(
            typeof detail === 'string' ? detail : this.lang.translate('faqAdmin.couldNotSave'),
          );
        },
      });
  }

  async deleteFaq(item: FaqItem): Promise<void> {
    const confirmed = await this.confirmDialog.confirm({
      title: this.lang.translate('faqAdmin.deleteTitle'),
      message: `${this.lang.translate('kb.deletePrefix')} "${item.question}"${this.lang.translate('kb.cannotUndo')}`,
      confirmLabel: this.lang.translate('common.delete'),
    });
    if (!confirmed) return;

    this.deleteError.set(null);
    this.deletingIds.update((s) => new Set(s).add(item.id));

    this.faqService.delete(item.id).subscribe({
      next: () => {
        this.deletingIds.update((s) => {
          const n = new Set(s);
          n.delete(item.id);
          return n;
        });
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.deleteError.set(
          typeof detail === 'string' ? detail : this.lang.translate('faqAdmin.couldNotDelete'),
        );
        this.deletingIds.update((s) => {
          const n = new Set(s);
          n.delete(item.id);
          return n;
        });
      },
    });
  }

  // ──────────── Error Solutions actions ────────────

  toggleEsUncategorizedOnly(): void {
    this.esUncategorizedOnly.update((v) => !v);
    this.esLoad();
  }

  esAddErrorSolution(): void {
    const errorText = this.esNewErrorText().trim();
    const solutionText = this.esNewSolutionText().trim();
    if (!errorText || !solutionText || this.esIsAdding()) return;

    this.esIsAdding.set(true);
    this.esAddError.set(null);

    this.errorSolutionsService.create(errorText, solutionText, this.esNewCategoryId() || null).subscribe({
      next: () => {
        this.esIsAdding.set(false);
        this.esNewErrorText.set('');
        this.esNewSolutionText.set('');
        this.esNewCategoryId.set('');
        this.esLoad();
      },
      error: (err: HttpErrorResponse) => {
        this.esIsAdding.set(false);
        const detail = err.error?.detail;
        this.esAddError.set(
          typeof detail === 'string' ? detail : this.lang.translate('errorSolutionsAdmin.couldNotAdd'),
        );
      },
    });
  }

  esStartEdit(item: ErrorSolutionItem): void {
    this.esEditingId.set(item.id);
    this.esEditErrorText.set(item.error_text);
    this.esEditSolutionText.set(item.solution_text);
    this.esEditCategoryId.set(item.category_id ?? '');
    this.esEditError.set(null);
  }

  esCancelEdit(): void {
    this.esEditingId.set(null);
    this.esEditErrorText.set('');
    this.esEditSolutionText.set('');
    this.esEditCategoryId.set('');
    this.esEditError.set(null);
  }

  esSaveEdit(item: ErrorSolutionItem): void {
    const errorText = this.esEditErrorText().trim();
    const solutionText = this.esEditSolutionText().trim();
    if (!errorText || !solutionText || this.esIsSavingEdit()) return;

    this.esIsSavingEdit.set(true);
    this.esEditError.set(null);

    this.errorSolutionsService
      .update(item.id, errorText, solutionText, this.esEditCategoryId() || null)
      .subscribe({
        next: () => {
          this.esIsSavingEdit.set(false);
          this.esEditingId.set(null);
          this.esEditErrorText.set('');
          this.esEditSolutionText.set('');
          this.esEditCategoryId.set('');
          this.esLoad();
        },
        error: (err: HttpErrorResponse) => {
          this.esIsSavingEdit.set(false);
          const detail = err.error?.detail;
          this.esEditError.set(
            typeof detail === 'string' ? detail : this.lang.translate('errorSolutionsAdmin.couldNotSave'),
          );
        },
      });
  }

  async esDeleteErrorSolution(item: ErrorSolutionItem): Promise<void> {
    const confirmed = await this.confirmDialog.confirm({
      title: this.lang.translate('errorSolutionsAdmin.deleteTitle'),
      message: `${this.lang.translate('kb.deletePrefix')} "${item.error_text}"${this.lang.translate('kb.cannotUndo')}`,
      confirmLabel: this.lang.translate('common.delete'),
    });
    if (!confirmed) return;

    this.esDeleteError.set(null);
    this.esDeletingIds.update((s) => new Set(s).add(item.id));

    this.errorSolutionsService.delete(item.id).subscribe({
      next: () => {
        this.esDeletingIds.update((s) => {
          const n = new Set(s);
          n.delete(item.id);
          return n;
        });
        this.esLoad();
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.esDeleteError.set(
          typeof detail === 'string' ? detail : this.lang.translate('errorSolutionsAdmin.couldNotDelete'),
        );
        this.esDeletingIds.update((s) => {
          const n = new Set(s);
          n.delete(item.id);
          return n;
        });
      },
    });
  }

  esOnImportFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = '';
    if (!file) return;
    this.esImportFile.set(file);
    this.esImportResultMessage.set(null);
    this.esImportError.set(null);
  }

  esImportFromExcel(): void {
    const file = this.esImportFile();
    if (!file || this.esIsImporting()) return;

    this.esIsImporting.set(true);
    this.esImportError.set(null);
    this.esImportResultMessage.set(null);

    this.errorSolutionsService.importExcel(file).subscribe({
      next: (res) => {
        this.esIsImporting.set(false);
        this.esImportFile.set(null);
        this.esImportResultMessage.set(
          `${this.lang.translate('errorSolutionsAdmin.importCreated')} ${res.created}, ` +
            `${this.lang.translate('errorSolutionsAdmin.importSkipped')} ${res.skipped}`,
        );
        this.esLoad();
      },
      error: (err: HttpErrorResponse) => {
        this.esIsImporting.set(false);
        const detail = err.error?.detail;
        this.esImportError.set(
          typeof detail === 'string' ? detail : this.lang.translate('errorSolutionsAdmin.importFailed'),
        );
      },
    });
  }

  private load(): void {
    this.isLoading.set(true);
    this.loadError.set(null);

    const list$ = this.uncategorizedOnly()
      ? this.faqService.listUncategorized()
      : this.faqService.list();

    list$.subscribe({
      next: (items) => {
        this.items.set(items);
        this.isLoading.set(false);
        this.page.set(1);
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading.set(false);
        const detail = err.error?.detail;
        this.loadError.set(
          typeof detail === 'string' ? detail : this.lang.translate('faqAdmin.couldNotLoad'),
        );
      },
    });
  }

  // ──────────── FAQ category actions ────────────

  private loadCategories(): void {
    this.categoriesLoading.set(true);
    this.categoriesLoadError.set(null);

    this.faqCategoryService.list().subscribe({
      next: (categories) => {
        this.categories.set(categories);
        this.categoriesLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.categoriesLoading.set(false);
        const detail = err.error?.detail;
        this.categoriesLoadError.set(
          typeof detail === 'string' ? detail : this.lang.translate('faqAdmin.couldNotLoadCategories'),
        );
      },
    });
  }

  addCategory(): void {
    const nameAr = this.newCategoryNameAr().trim();
    const nameEn = this.newCategoryNameEn().trim();
    if (!nameAr || !nameEn || this.isAddingCategory()) return;

    this.isAddingCategory.set(true);
    this.addCategoryError.set(null);

    this.faqCategoryService.create(nameAr, nameEn, null).subscribe({
      next: () => {
        this.isAddingCategory.set(false);
        this.newCategoryNameAr.set('');
        this.newCategoryNameEn.set('');
        this.loadCategories();
      },
      error: (err: HttpErrorResponse) => {
        this.isAddingCategory.set(false);
        const detail = err.error?.detail;
        this.addCategoryError.set(
          typeof detail === 'string' ? detail : this.lang.translate('faqAdmin.couldNotAddCategory'),
        );
      },
    });
  }

  startEditCategory(category: FaqCategory): void {
    this.editingCategoryId.set(category.id);
    this.editCategoryNameAr.set(category.name_ar);
    this.editCategoryNameEn.set(category.name_en);
    this.editCategoryDisplayOrder.set(category.display_order);
    this.editCategoryError.set(null);
  }

  cancelEditCategory(): void {
    this.editingCategoryId.set(null);
    this.editCategoryNameAr.set('');
    this.editCategoryNameEn.set('');
    this.editCategoryDisplayOrder.set(null);
    this.editCategoryError.set(null);
  }

  saveEditCategory(category: FaqCategory): void {
    const nameAr = this.editCategoryNameAr().trim();
    const nameEn = this.editCategoryNameEn().trim();
    if (!nameAr || !nameEn || this.isSavingCategoryEdit()) return;

    this.isSavingCategoryEdit.set(true);
    this.editCategoryError.set(null);

    this.faqCategoryService
      .update(category.id, nameAr, nameEn, this.editCategoryDisplayOrder())
      .subscribe({
        next: () => {
          this.isSavingCategoryEdit.set(false);
          this.cancelEditCategory();
          this.loadCategories();
        },
        error: (err: HttpErrorResponse) => {
          this.isSavingCategoryEdit.set(false);
          const detail = err.error?.detail;
          this.editCategoryError.set(
            typeof detail === 'string' ? detail : this.lang.translate('faqAdmin.couldNotSaveCategory'),
          );
        },
      });
  }

  /** Moves a category one slot up/down in display_order by swapping it with
   * its neighbor — simplest reordering UI given no drag-and-drop library is
   * used anywhere else in this codebase. */
  moveCategory(category: FaqCategory, direction: -1 | 1): void {
    const ordered = [...this.categories()].sort((a, b) => a.display_order - b.display_order);
    const index = ordered.findIndex((c) => c.id === category.id);
    const neighborIndex = index + direction;
    if (index === -1 || neighborIndex < 0 || neighborIndex >= ordered.length) return;

    const neighbor = ordered[neighborIndex];
    this.faqCategoryService
      .update(category.id, category.name_ar, category.name_en, neighbor.display_order)
      .subscribe({
        next: () => {
          this.faqCategoryService
            .update(neighbor.id, neighbor.name_ar, neighbor.name_en, category.display_order)
            .subscribe({ next: () => this.loadCategories(), error: () => this.loadCategories() });
        },
        error: (err: HttpErrorResponse) => {
          const detail = err.error?.detail;
          this.editCategoryError.set(
            typeof detail === 'string' ? detail : this.lang.translate('faqAdmin.couldNotSaveCategory'),
          );
        },
      });
  }

  async deleteCategory(category: FaqCategory): Promise<void> {
    const confirmed = await this.confirmDialog.confirm({
      title: this.lang.translate('faqAdmin.deleteCategoryTitle'),
      message: `${this.lang.translate('kb.deletePrefix')} "${category.name_en}"${this.lang.translate('faqAdmin.deleteCategoryWarning')}`,
      confirmLabel: this.lang.translate('common.delete'),
    });
    if (!confirmed) return;

    this.deleteCategoryError.set(null);
    this.deletingCategoryIds.update((s) => new Set(s).add(category.id));

    this.faqCategoryService.delete(category.id).subscribe({
      next: () => {
        this.deletingCategoryIds.update((s) => {
          const n = new Set(s);
          n.delete(category.id);
          return n;
        });
        this.loadCategories();
        this.load(); // affected FAQs just fell back to uncategorized
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.deleteCategoryError.set(
          typeof detail === 'string' ? detail : this.lang.translate('faqAdmin.couldNotDeleteCategory'),
        );
        this.deletingCategoryIds.update((s) => {
          const n = new Set(s);
          n.delete(category.id);
          return n;
        });
      },
    });
  }

  private esLoad(): void {
    this.esIsLoading.set(true);
    this.esLoadError.set(null);

    const list$ = this.esUncategorizedOnly()
      ? this.errorSolutionsService.listUncategorized()
      : this.errorSolutionsService.list();

    list$.subscribe({
      next: (items) => {
        this.esItems.set(items);
        this.esIsLoading.set(false);
        this.esPage.set(1);
      },
      error: (err: HttpErrorResponse) => {
        this.esIsLoading.set(false);
        const detail = err.error?.detail;
        this.esLoadError.set(
          typeof detail === 'string' ? detail : this.lang.translate('errorSolutionsAdmin.couldNotLoad'),
        );
      },
    });
  }
}
