import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl, SafeUrl } from '@angular/platform-browser';
import { environment } from '../../../../environments/environment';
import {
  Category,
  CategoryContent,
  CategoryDocument,
  CategoryMediaItem,
  LinkType,
  SuggestedQuestion,
} from '../../../core/models/category.models';
import { ExcelRow, ExcelTable } from '../../../core/models/excel.models';
import { CategoriesService } from '../../../core/services/categories.service';
import { ConfirmDialogService } from '../../../core/services/confirm-dialog.service';
import { DocumentsService } from '../../../core/services/documents.service';
import { ExcelService } from '../../../core/services/excel.service';
import { LanguageService } from '../../../core/services/language.service';
import { MediaService } from '../../../core/services/media.service';
import { SuggestedQuestionsService } from '../../../core/services/suggested-questions.service';
import { DropdownOption, DropdownSelect } from '../../../shared/dropdown-select/dropdown-select';
import { Pagination } from '../../../shared/pagination/pagination';
import { DisplayNamePipe, resolveDisplayName } from '../../../shared/pipes/display-name.pipe';

const DOC_EXTENSIONS = ['.pdf', '.docx', '.xlsx', '.txt', '.pptx', '.ppt'];
const MEDIA_EXTENSIONS = ['.mp4', '.mov', '.webm', '.jpg', '.jpeg', '.png', '.gif', '.webp'];
const LIST_PAGE_SIZE = 10;

type LibrarySubTab = 'files' | 'images' | 'videos' | 'links' | 'questions';

interface DocUploadItem {
  localId: string;
  filename: string;
  status: 'uploading' | 'error';
  errorMessage?: string;
}

/** True if the string is a syntactically valid http(s) URL. */
function isValidHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

/** Extracts the video ID from a youtube.com/watch?v= or youtu.be/ URL, or null if not a match. */
function extractYoutubeId(url: string): string | null {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, '');

    if (host === 'youtu.be') {
      return parsed.pathname.slice(1).split('/')[0] || null;
    }
    if (host === 'youtube.com' && parsed.pathname === '/watch') {
      return parsed.searchParams.get('v');
    }
    return null;
  } catch {
    return null;
  }
}

/** True if a cell value is empty/whitespace-only. */
function isBlankCell(value: string | undefined): boolean {
  return (value ?? '').trim() === '';
}

/**
 * Excel files commonly have formatted-but-unused columns/rows that openpyxl
 * still reports as part of the used range, so the API can return more
 * columns/rows than the sheet's real data — and since every row inserted
 * during one upload shares the same DB timestamp (see excel_rows.created_at),
 * the API's row order isn't guaranteed to put that padding at the end.
 * Filters out any column, wherever it appears, whose header is blank and
 * whose value is blank in every row, so the table renders exactly the real
 * data size instead of a padded grid.
 */
function computeVisibleColumns(table: ExcelTable | null): string[] {
  if (!table) return [];
  return table.columns.filter((col) => {
    if (!isBlankCell(col)) return true;
    return table.rows.some((r) => !isBlankCell(r.row_data[col]));
  });
}

/** Filters out any row, wherever it appears, that's blank across every visible column. */
function computeVisibleRows(table: ExcelTable | null, visibleColumns: string[]): ExcelRow[] {
  if (!table) return [];
  return table.rows.filter((row) => visibleColumns.some((col) => !isBlankCell(row.row_data[col])));
}

const LINK_TYPE_OPTIONS: DropdownOption[] = [
  { value: 'youtube', label: 'YouTube' },
  { value: 'google_drive', label: 'Google Drive' },
  { value: 'other', label: 'Other' },
];

@Component({
  selector: 'app-knowledge-base',
  imports: [FormsModule, Pagination, DropdownSelect, DisplayNamePipe],
  templateUrl: './knowledge-base.html',
  styleUrl: './knowledge-base.scss',
})
export class KnowledgeBase implements OnInit, OnDestroy {
  private readonly categoriesService = inject(CategoriesService);
  private readonly confirmDialog = inject(ConfirmDialogService);
  private readonly http = inject(HttpClient);
  private readonly documentsService = inject(DocumentsService);
  private readonly mediaService = inject(MediaService);
  private readonly suggestedQuestionsService = inject(SuggestedQuestionsService);
  private readonly excelService = inject(ExcelService);
  private readonly sanitizer = inject(DomSanitizer);
  readonly lang = inject(LanguageService);

  readonly categories = signal<Category[]>([]);
  readonly categoriesError = signal<string | null>(null);
  readonly selectedCategory = signal<Category | null>(null);
  readonly newCategoryName = signal('');
  readonly isAddingCategory = signal(false);
  readonly addCategoryError = signal<string | null>(null);
  readonly togglingPublishIds = signal<Set<string>>(new Set());
  readonly publishErrors = signal<Map<string, string>>(new Map());
  readonly isDeletingCategory = signal(false);
  readonly deleteCategoryError = signal<string | null>(null);

  readonly editingCategoryId = signal<string | null>(null);
  readonly editCategoryName = signal('');
  readonly isRenamingCategory = signal(false);
  readonly renameCategoryError = signal<string | null>(null);

  readonly content = signal<CategoryContent | null>(null);
  readonly contentLoading = signal(false);
  readonly contentError = signal<string | null>(null);

  readonly docUploads = signal<DocUploadItem[]>([]);
  readonly isDocUploading = signal(false);
  readonly docQueueLength = signal(0);
  readonly deletingDocIds = signal<Set<string>>(new Set());
  readonly deleteDocError = signal<string | null>(null);
  readonly downloadDocError = signal<string | null>(null);

  readonly editingDocId = signal<string | null>(null);
  readonly editDocName = signal('');
  readonly isRenamingDoc = signal(false);
  readonly renameDocError = signal<string | null>(null);

  readonly editingMediaId = signal<string | null>(null);
  readonly editMediaName = signal('');
  readonly isRenamingMedia = signal(false);
  readonly renameMediaError = signal<string | null>(null);

  readonly docStagedFiles = signal<File[]>([]);
  readonly docFileLabel = computed(() => {
    const files = this.docStagedFiles();
    if (files.length === 0) return this.lang.translate('kb.chooseFiles');
    if (files.length === 1) return files[0].name;
    return this.lang.translate('kb.filesSelected').replace('{n}', '' + files.length);
  });
  readonly docStagedFileNames = computed(() =>
    this.docStagedFiles()
      .map((f) => f.name)
      .join(', '),
  );

  readonly docLinkedMediaId = signal<string>('');
  readonly docDisplayName = signal('');
  readonly linkableMediaItems = computed(() =>
    (this.content()?.media ?? []).filter(
      (m) => m.media_type === 'link' || m.media_type.startsWith('video'),
    ),
  );
  readonly linkedMediaOptions = computed<DropdownOption[]>(() => [
    { value: '', label: this.lang.translate('kb.none') },
    ...this.linkableMediaItems().map((m) => ({
      value: m.id,
      label: resolveDisplayName(m),
    })),
  ]);

  readonly mediaFile = signal<File | null>(null);
  readonly mediaDescription = signal('');
  readonly mediaDisplayName = signal('');
  readonly mediaFileError = signal<string | null>(null);
  readonly isUploadingMedia = signal(false);
  readonly deletingMediaIds = signal<Set<string>>(new Set());
  readonly deleteMediaError = signal<string | null>(null);

  readonly linkUrl = signal('');
  readonly linkDescription = signal('');
  readonly linkDisplayName = signal('');
  readonly linkType = signal<LinkType>('other');
  readonly linkError = signal<string | null>(null);
  readonly isAddingLink = signal(false);
  readonly linkTypeOptions = computed<DropdownOption[]>(() =>
    LINK_TYPE_OPTIONS.map((o) =>
      o.value === 'other' ? { ...o, label: this.lang.translate('kb.linkTypeOther') } : o,
    ),
  );

  readonly linkUrlError = computed(() => {
    const value = this.linkUrl().trim();
    if (!value) return null;
    return isValidHttpUrl(value) ? null : this.lang.translate('kb.invalidUrl');
  });

  readonly isUploadingAny = computed(
    () => this.isDocUploading() || this.isUploadingMedia() || this.isAddingLink(),
  );

  private readonly docQueue: File[] = [];

  readonly suggestedQuestions = signal<SuggestedQuestion[]>([]);
  readonly sqLoading = signal(false);
  readonly sqError = signal<string | null>(null);
  readonly newQuestionText = signal('');
  readonly newAnswerText = signal('');
  readonly isAddingQuestion = signal(false);
  readonly addQuestionError = signal<string | null>(null);
  readonly deletingQuestionIds = signal<Set<string>>(new Set());
  readonly deleteQuestionError = signal<string | null>(null);

  readonly editingQuestionId = signal<string | null>(null);
  readonly editQuestionText = signal('');
  readonly editAnswerText = signal('');
  readonly isSavingQuestion = signal(false);
  readonly editQuestionError = signal<string | null>(null);

  readonly sqPage = signal(1);
  readonly sqTotalPages = computed(() =>
    Math.max(1, Math.ceil(this.suggestedQuestions().length / LIST_PAGE_SIZE)),
  );
  readonly pagedSuggestedQuestions = computed(() => {
    const start = (this.sqPage() - 1) * LIST_PAGE_SIZE;
    return this.suggestedQuestions().slice(start, start + LIST_PAGE_SIZE);
  });

  // ──────────── Manage / Library tabs ────────────

  readonly activeTab = signal<'manage' | 'library'>('manage');
  readonly librarySubTab = signal<LibrarySubTab>('files');

  readonly libraryDocuments = computed(() => this.content()?.documents ?? []);
  readonly libraryImages = computed(() =>
    (this.content()?.media ?? []).filter((m) => m.media_type === 'image'),
  );
  readonly libraryVideos = computed(() =>
    (this.content()?.media ?? []).filter((m) => m.media_type.startsWith('video')),
  );
  readonly libraryLinks = computed(() =>
    (this.content()?.media ?? []).filter((m) => m.media_type === 'link'),
  );

  readonly filesPage = signal(1);
  readonly filesTotalPages = computed(() =>
    Math.max(1, Math.ceil(this.libraryDocuments().length / LIST_PAGE_SIZE)),
  );
  readonly pagedDocuments = computed(() => {
    const start = (this.filesPage() - 1) * LIST_PAGE_SIZE;
    return this.libraryDocuments().slice(start, start + LIST_PAGE_SIZE);
  });

  // ──────────── Excel table view (spreadsheet documents) ────────────

  readonly expandedExcelDocId = signal<string | null>(null);
  readonly excelTable = signal<ExcelTable | null>(null);
  readonly excelTableLoading = signal(false);
  readonly excelTableError = signal<string | null>(null);

  // excelTable is trimmed of blank trailing rows/columns once, when loaded
  // (see toggleExcelTable) — these are plain accessors, not re-trimmed on
  // every read, so a freshly appended row never ends up behind leftover
  // blank padding that trimming-on-every-render would otherwise re-reveal.
  readonly visibleExcelColumns = computed(() => this.excelTable()?.columns ?? []);
  readonly visibleExcelRows = computed(() => this.excelTable()?.rows ?? []);

  readonly editingCell = signal<{ rowId: string; column: string } | null>(null);
  readonly editingCellValue = signal('');
  readonly savingRowIds = signal<Set<string>>(new Set());
  readonly deletingRowIds = signal<Set<string>>(new Set());
  readonly rowActionError = signal<string | null>(null);

  readonly newRowValues = signal<Record<string, string>>({});
  readonly isAddingRow = signal(false);
  readonly addRowError = signal<string | null>(null);

  readonly imagesPage = signal(1);
  readonly imagesTotalPages = computed(() =>
    Math.max(1, Math.ceil(this.libraryImages().length / LIST_PAGE_SIZE)),
  );
  readonly pagedImages = computed(() => {
    const start = (this.imagesPage() - 1) * LIST_PAGE_SIZE;
    return this.libraryImages().slice(start, start + LIST_PAGE_SIZE);
  });

  readonly videosPage = signal(1);
  readonly videosTotalPages = computed(() =>
    Math.max(1, Math.ceil(this.libraryVideos().length / LIST_PAGE_SIZE)),
  );
  readonly pagedVideos = computed(() => {
    const start = (this.videosPage() - 1) * LIST_PAGE_SIZE;
    return this.libraryVideos().slice(start, start + LIST_PAGE_SIZE);
  });

  readonly linksPage = signal(1);
  readonly linksTotalPages = computed(() =>
    Math.max(1, Math.ceil(this.libraryLinks().length / LIST_PAGE_SIZE)),
  );
  readonly pagedLinks = computed(() => {
    const start = (this.linksPage() - 1) * LIST_PAGE_SIZE;
    return this.libraryLinks().slice(start, start + LIST_PAGE_SIZE);
  });

  private readonly rawVideoObjectUrls: string[] = [];
  readonly videoPreviewUrls = signal<Map<string, SafeUrl>>(new Map());
  private readonly loadingVideoPreviewIds = new Set<string>();

  constructor() {
    // Lazily fetch a blob preview for every video/image visible on the
    // current sub-tab page (guarded so each item is only fetched once).
    effect(() => {
      for (const item of [...this.pagedVideos(), ...this.pagedImages()]) {
        this.ensureVideoPreview(item);
      }
    });
  }

  ngOnInit(): void {
    this.loadCategories();
  }

  ngOnDestroy(): void {
    this.rawVideoObjectUrls.forEach((url) => URL.revokeObjectURL(url));
  }

  setActiveTab(tab: 'manage' | 'library'): void {
    this.activeTab.set(tab);
  }

  setLibrarySubTab(tab: LibrarySubTab): void {
    this.librarySubTab.set(tab);
  }

  selectCategory(cat: Category): void {
    this.selectedCategory.set(cat);
    this.content.set(null);
    this.contentError.set(null);
    this.deleteDocError.set(null);
    this.editingDocId.set(null);
    this.editDocName.set('');
    this.isRenamingDoc.set(false);
    this.renameDocError.set(null);
    this.editingMediaId.set(null);
    this.editMediaName.set('');
    this.isRenamingMedia.set(false);
    this.renameMediaError.set(null);
    this.docUploads.set([]);
    this.docQueue.length = 0;
    this.docQueueLength.set(0);
    this.docStagedFiles.set([]);
    this.docLinkedMediaId.set('');
    this.docDisplayName.set('');
    this.mediaFile.set(null);
    this.mediaDescription.set('');
    this.mediaDisplayName.set('');
    this.mediaFileError.set(null);
    this.deleteMediaError.set(null);
    this.linkUrl.set('');
    this.linkDescription.set('');
    this.linkDisplayName.set('');
    this.linkType.set('other');
    this.linkError.set(null);
    this.suggestedQuestions.set([]);
    this.sqError.set(null);
    this.newQuestionText.set('');
    this.newAnswerText.set('');
    this.addQuestionError.set(null);
    this.deleteQuestionError.set(null);
    this.editingQuestionId.set(null);
    this.editQuestionText.set('');
    this.editAnswerText.set('');
    this.editQuestionError.set(null);
    this.deleteCategoryError.set(null);
    this.expandedExcelDocId.set(null);
    this.excelTable.set(null);
    this.excelTableLoading.set(false);
    this.excelTableError.set(null);
    this.editingCell.set(null);
    this.editingCellValue.set('');
    this.savingRowIds.set(new Set());
    this.deletingRowIds.set(new Set());
    this.rowActionError.set(null);
    this.newRowValues.set({});
    this.isAddingRow.set(false);
    this.addRowError.set(null);
    this.activeTab.set('manage');
    this.librarySubTab.set('files');
    this.sqPage.set(1);
    this.filesPage.set(1);
    this.videosPage.set(1);
    this.linksPage.set(1);
    this.clearVideoPreviews();
    this.loadContent(cat.id);
    this.loadSuggestedQuestions(cat.id);
  }

  addCategory(): void {
    const name = this.newCategoryName().trim();
    if (!name || this.isAddingCategory()) return;

    this.isAddingCategory.set(true);
    this.addCategoryError.set(null);

    this.categoriesService.create(name).subscribe({
      next: (cat) => {
        this.categories.update((list) => [...list, cat]);
        this.newCategoryName.set('');
        this.isAddingCategory.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.isAddingCategory.set(false);
        if (err.status === 409) {
          this.addCategoryError.set(`"${name}" ${this.lang.translate('kb.alreadyExists')}`);
        } else {
          const detail = err.error?.detail;
          this.addCategoryError.set(
            typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotCreateCategory'),
          );
        }
      },
    });
  }

  publishCategory(cat: Category): void {
    if (this.togglingPublishIds().has(cat.id)) return;

    this.clearPublishError(cat.id);
    this.togglingPublishIds.update((s) => new Set(s).add(cat.id));

    this.categoriesService.publish(cat.id).subscribe({
      next: () => {
        this.endTogglingPublish(cat.id);
        this.loadCategories();
      },
      error: (err: HttpErrorResponse) => {
        this.endTogglingPublish(cat.id);
        const detail = err.error?.detail;
        this.setPublishError(
          cat.id,
          err.status === 400
            ? this.lang.translate('kb.cannotPublishEmpty')
            : typeof detail === 'string'
              ? detail
              : this.lang.translate('kb.couldNotPublish'),
        );
      },
    });
  }

  unpublishCategory(cat: Category): void {
    if (this.togglingPublishIds().has(cat.id)) return;

    this.clearPublishError(cat.id);
    this.togglingPublishIds.update((s) => new Set(s).add(cat.id));

    this.categoriesService.unpublish(cat.id).subscribe({
      next: () => {
        this.endTogglingPublish(cat.id);
        this.loadCategories();
      },
      error: (err: HttpErrorResponse) => {
        this.endTogglingPublish(cat.id);
        const detail = err.error?.detail;
        this.setPublishError(
          cat.id,
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotUnpublish'),
        );
      },
    });
  }

  async deleteCategory(cat: Category): Promise<void> {
    if (this.isDeletingCategory()) return;

    const confirmed = await this.confirmDialog.confirm({
      title: this.lang.translate('kb.deleteCategoryTitle'),
      message: this.lang.translate('kb.deleteCategoryMsg'),
      confirmLabel: this.lang.translate('common.delete'),
    });
    if (!confirmed) return;

    this.isDeletingCategory.set(true);
    this.deleteCategoryError.set(null);

    this.categoriesService.delete(cat.id).subscribe({
      next: () => {
        this.isDeletingCategory.set(false);
        this.selectedCategory.set(null);
        this.content.set(null);
        this.loadCategories();
      },
      error: (err: HttpErrorResponse) => {
        this.isDeletingCategory.set(false);
        const detail = err.error?.detail;
        this.deleteCategoryError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotDeleteCategory'),
        );
      },
    });
  }

  startRenameCategory(cat: Category): void {
    this.editingCategoryId.set(cat.id);
    this.editCategoryName.set(cat.name);
    this.renameCategoryError.set(null);
  }

  cancelRenameCategory(): void {
    this.editingCategoryId.set(null);
    this.editCategoryName.set('');
    this.renameCategoryError.set(null);
  }

  saveRenameCategory(cat: Category): void {
    const name = this.editCategoryName().trim();
    if (!name || this.isRenamingCategory()) return;

    this.isRenamingCategory.set(true);
    this.renameCategoryError.set(null);

    this.http
      .patch<Category>(`${environment.apiBaseUrl}/categories/${cat.id}`, { name })
      .subscribe({
        next: () => {
          this.isRenamingCategory.set(false);
          this.editingCategoryId.set(null);
          this.editCategoryName.set('');
          this.loadCategories();
        },
        error: (err: HttpErrorResponse) => {
          this.isRenamingCategory.set(false);
          const detail = err.error?.detail;
          this.renameCategoryError.set(
            typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotRenameCategory'),
          );
        },
      });
  }

  onDocFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = input.files;
    if (!files || files.length === 0) return;
    this.docStagedFiles.update((list) => [...list, ...Array.from(files)]);
    input.value = '';
  }

  submitDocUpload(): void {
    const staged = this.docStagedFiles();
    if (staged.length === 0 || this.isUploadingAny()) return;

    this.docQueue.push(...staged);
    this.docQueueLength.set(this.docQueue.length);
    this.docStagedFiles.set([]);
    this.processDocQueue();
  }

  async deleteDocument(doc: CategoryDocument): Promise<void> {
    const confirmed = await this.confirmDialog.confirm({
      title: this.lang.translate('kb.deleteDocTitle'),
      message: `${this.lang.translate('kb.deletePrefix')} "${resolveDisplayName(doc)}"${this.lang.translate('kb.cannotUndo')}`,
      confirmLabel: this.lang.translate('common.delete'),
    });
    if (!confirmed) return;

    this.deleteDocError.set(null);
    this.deletingDocIds.update((s) => new Set(s).add(doc.id));

    this.documentsService.delete(doc.id).subscribe({
      next: () => {
        this.deletingDocIds.update((s) => {
          const n = new Set(s);
          n.delete(doc.id);
          return n;
        });
        this.refreshContent();
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.deleteDocError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotDeleteFile'),
        );
        this.deletingDocIds.update((s) => {
          const n = new Set(s);
          n.delete(doc.id);
          return n;
        });
      },
    });
  }

  startRenameDoc(doc: CategoryDocument): void {
    this.editingDocId.set(doc.id);
    this.editDocName.set(resolveDisplayName(doc));
    this.renameDocError.set(null);
  }

  cancelRenameDoc(): void {
    this.editingDocId.set(null);
    this.editDocName.set('');
    this.renameDocError.set(null);
  }

  saveRenameDoc(doc: CategoryDocument): void {
    const name = this.editDocName().trim();
    if (!name || this.isRenamingDoc()) return;

    this.isRenamingDoc.set(true);
    this.renameDocError.set(null);

    this.documentsService.rename(doc.id, name).subscribe({
      next: () => {
        this.isRenamingDoc.set(false);
        this.editingDocId.set(null);
        this.editDocName.set('');
        this.content.update((c) =>
          c
            ? {
                ...c,
                documents: c.documents.map((d) =>
                  d.id === doc.id ? { ...d, display_name: name } : d,
                ),
              }
            : c,
        );
      },
      error: (err: HttpErrorResponse) => {
        this.isRenamingDoc.set(false);
        const detail = err.error?.detail;
        this.renameDocError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotRenameFile'),
        );
      },
    });
  }

  /**
   * Downloads a document to the user's device. Spreadsheet documents have a
   * separate expand/collapse control (toggleExcelTable) for the inline table.
   */
  openDocument(doc: CategoryDocument): void {
    if (!doc.has_file) return;
    this.downloadDocError.set(null);
    this.documentsService.downloadFile(doc.id, resolveDisplayName(doc), (err: HttpErrorResponse) => {
      this.downloadDocError.set(
        err.status === 404
          ? this.lang.translate('kb.fileMissingOnServer')
          : this.lang.translate('kb.couldNotDownloadFile'),
      );
    });
  }

  toggleExcelTable(doc: CategoryDocument): void {
    if (this.expandedExcelDocId() === doc.id) {
      this.closeExcelTable();
      return;
    }

    this.expandedExcelDocId.set(doc.id);
    this.excelTable.set(null);
    this.excelTableError.set(null);
    this.rowActionError.set(null);
    this.addRowError.set(null);
    this.editingCell.set(null);
    this.editingCellValue.set('');
    this.excelTableLoading.set(true);

    this.excelService.getTable(doc.id).subscribe({
      next: (table) => {
        const columns = computeVisibleColumns(table);
        const rows = computeVisibleRows(table, columns);
        this.excelTable.set({ columns, rows });
        this.newRowValues.set(this.emptyRowValues(columns));
        this.excelTableLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.excelTableError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotLoadExcelTable'),
        );
        this.excelTableLoading.set(false);
      },
    });
  }

  closeExcelTable(): void {
    this.expandedExcelDocId.set(null);
    this.excelTable.set(null);
    this.excelTableLoading.set(false);
    this.excelTableError.set(null);
    this.editingCell.set(null);
    this.editingCellValue.set('');
    this.rowActionError.set(null);
    this.newRowValues.set({});
    this.addRowError.set(null);
  }

  isEditingCell(rowId: string, column: string): boolean {
    const cell = this.editingCell();
    return !!cell && cell.rowId === rowId && cell.column === column;
  }

  startEditCell(row: ExcelRow, column: string): void {
    this.editingCell.set({ rowId: row.id, column });
    this.editingCellValue.set(row.row_data[column] ?? '');
  }

  cancelEditCell(): void {
    this.editingCell.set(null);
    this.editingCellValue.set('');
  }

  saveEditCell(row: ExcelRow): void {
    const cell = this.editingCell();
    if (!cell || cell.rowId !== row.id) return;

    const column = cell.column;
    const newValue = this.editingCellValue();
    const originalValue = row.row_data[column] ?? '';

    this.editingCell.set(null);
    this.editingCellValue.set('');

    if (newValue === originalValue) return;

    const updatedRowData = { ...row.row_data, [column]: newValue };

    this.rowActionError.set(null);
    this.savingRowIds.update((s) => new Set(s).add(row.id));

    this.excelService.updateRow(row.id, updatedRowData).subscribe({
      next: (updated) => {
        this.savingRowIds.update((s) => {
          const n = new Set(s);
          n.delete(row.id);
          return n;
        });
        this.excelTable.update((table) =>
          table ? { ...table, rows: table.rows.map((r) => (r.id === row.id ? updated : r)) } : table,
        );
      },
      error: (err: HttpErrorResponse) => {
        this.savingRowIds.update((s) => {
          const n = new Set(s);
          n.delete(row.id);
          return n;
        });
        const detail = err.error?.detail;
        this.rowActionError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotSaveCell'),
        );
      },
    });
  }

  updateNewRowValue(column: string, value: string): void {
    this.newRowValues.update((v) => ({ ...v, [column]: value }));
  }

  submitNewRow(): void {
    const docId = this.expandedExcelDocId();
    const table = this.excelTable();
    if (!docId || !table || this.isAddingRow()) return;

    this.isAddingRow.set(true);
    this.addRowError.set(null);

    this.excelService.addRow(docId, this.newRowValues()).subscribe({
      next: (row) => {
        this.isAddingRow.set(false);
        this.excelTable.update((t) => (t ? { ...t, rows: [...t.rows, row] } : t));
        this.newRowValues.set(this.emptyRowValues(this.visibleExcelColumns()));
      },
      error: (err: HttpErrorResponse) => {
        this.isAddingRow.set(false);
        const detail = err.error?.detail;
        this.addRowError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotAddRow'),
        );
      },
    });
  }

  async deleteExcelRow(row: ExcelRow): Promise<void> {
    const confirmed = await this.confirmDialog.confirm({
      title: this.lang.translate('kb.deleteRowTitle'),
      message: `${this.lang.translate('kb.deletePrefix')} ${this.lang.translate('kb.thisRow')}${this.lang.translate('kb.cannotUndo')}`,
      confirmLabel: this.lang.translate('common.delete'),
    });
    if (!confirmed) return;

    this.rowActionError.set(null);
    this.deletingRowIds.update((s) => new Set(s).add(row.id));

    this.excelService.deleteRow(row.id).subscribe({
      next: () => {
        this.deletingRowIds.update((s) => {
          const n = new Set(s);
          n.delete(row.id);
          return n;
        });
        this.excelTable.update((table) =>
          table ? { ...table, rows: table.rows.filter((r) => r.id !== row.id) } : table,
        );
      },
      error: (err: HttpErrorResponse) => {
        this.deletingRowIds.update((s) => {
          const n = new Set(s);
          n.delete(row.id);
          return n;
        });
        const detail = err.error?.detail;
        this.rowActionError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotDeleteRow'),
        );
      },
    });
  }

  private emptyRowValues(columns: string[]): Record<string, string> {
    const values: Record<string, string> = {};
    for (const col of columns) values[col] = '';
    return values;
  }

  onMediaFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = '';
    if (!file) return;
    if (!this.hasExt(file.name, MEDIA_EXTENSIONS)) {
      this.mediaFileError.set(this.lang.translate('kb.unsupportedMediaType'));
      this.mediaFile.set(null);
      return;
    }
    this.mediaFileError.set(null);
    this.mediaFile.set(file);
  }

  submitMedia(): void {
    const file = this.mediaFile();
    const desc = this.mediaDescription().trim();
    const cat = this.selectedCategory();
    if (!file || !desc || !cat || this.isUploadingAny()) return;

    this.isUploadingMedia.set(true);
    this.mediaFileError.set(null);

    const displayName = this.mediaDisplayName().trim() || undefined;

    this.mediaService.upload(file, desc, cat.id, displayName).subscribe({
      next: () => {
        this.isUploadingMedia.set(false);
        this.mediaFile.set(null);
        this.mediaDescription.set('');
        this.mediaDisplayName.set('');
        this.refreshContent();
      },
      error: (err: HttpErrorResponse) => {
        this.isUploadingMedia.set(false);
        const detail = err.error?.detail;
        this.mediaFileError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.uploadFailed'),
        );
      },
    });
  }

  onLinkTypeChange(value: string): void {
    this.linkType.set(value as LinkType);
  }

  submitLink(): void {
    const url = this.linkUrl().trim();
    const desc = this.linkDescription().trim();
    const cat = this.selectedCategory();
    if (!url || !desc || !cat || this.isUploadingAny() || this.linkUrlError()) return;

    this.isAddingLink.set(true);
    this.linkError.set(null);

    const displayName = this.linkDisplayName().trim() || undefined;

    this.mediaService.addLink(url, desc, cat.id, this.linkType(), displayName).subscribe({
      next: () => {
        this.isAddingLink.set(false);
        this.linkUrl.set('');
        this.linkDescription.set('');
        this.linkDisplayName.set('');
        this.linkType.set('other');
        this.refreshContent();
      },
      error: (err: HttpErrorResponse) => {
        this.isAddingLink.set(false);
        const detail = err.error?.detail;
        this.linkError.set(typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotAddLink'));
      },
    });
  }

  async deleteMedia(item: CategoryMediaItem): Promise<void> {
    const confirmed = await this.confirmDialog.confirm({
      title: this.lang.translate('kb.deleteMediaTitle'),
      message: `${this.lang.translate('kb.deletePrefix')} "${resolveDisplayName(item)}"${this.lang.translate('kb.cannotUndo')}`,
      confirmLabel: this.lang.translate('common.delete'),
    });
    if (!confirmed) return;

    this.deleteMediaError.set(null);
    this.deletingMediaIds.update((s) => new Set(s).add(item.id));

    this.mediaService.delete(item.id).subscribe({
      next: () => {
        this.deletingMediaIds.update((s) => {
          const n = new Set(s);
          n.delete(item.id);
          return n;
        });
        this.refreshContent();
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.deleteMediaError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotDeleteMedia'),
        );
        this.deletingMediaIds.update((s) => {
          const n = new Set(s);
          n.delete(item.id);
          return n;
        });
      },
    });
  }

  startRenameMedia(item: CategoryMediaItem): void {
    this.editingMediaId.set(item.id);
    this.editMediaName.set(resolveDisplayName(item));
    this.renameMediaError.set(null);
  }

  cancelRenameMedia(): void {
    this.editingMediaId.set(null);
    this.editMediaName.set('');
    this.renameMediaError.set(null);
  }

  saveRenameMedia(item: CategoryMediaItem): void {
    const name = this.editMediaName().trim();
    if (!name || this.isRenamingMedia()) return;

    this.isRenamingMedia.set(true);
    this.renameMediaError.set(null);

    this.mediaService.rename(item.id, name).subscribe({
      next: () => {
        this.isRenamingMedia.set(false);
        this.editingMediaId.set(null);
        this.editMediaName.set('');
        this.content.update((c) =>
          c
            ? {
                ...c,
                media: c.media.map((m) => (m.id === item.id ? { ...m, display_name: name } : m)),
              }
            : c,
        );
      },
      error: (err: HttpErrorResponse) => {
        this.isRenamingMedia.set(false);
        const detail = err.error?.detail;
        this.renameMediaError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotRenameMedia'),
        );
      },
    });
  }

  addSuggestedQuestion(questionValue: string, answerValue: string): void {
    const question = questionValue.trim();
    const answer = answerValue.trim();
    const cat = this.selectedCategory();
    if (!question || !cat || this.isAddingQuestion()) return;

    this.isAddingQuestion.set(true);
    this.addQuestionError.set(null);

    this.suggestedQuestionsService.create(cat.id, question, answer).subscribe({
      next: () => {
        this.isAddingQuestion.set(false);
        this.newQuestionText.set('');
        this.newAnswerText.set('');
        this.refreshSuggestedQuestions();
      },
      error: (err: HttpErrorResponse) => {
        this.isAddingQuestion.set(false);
        const detail = err.error?.detail;
        this.addQuestionError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotAddQuestion'),
        );
      },
    });
  }

  async deleteSuggestedQuestion(q: SuggestedQuestion): Promise<void> {
    const confirmed = await this.confirmDialog.confirm({
      title: this.lang.translate('kb.deleteQuestionTitle'),
      message: `${this.lang.translate('kb.deletePrefix')} "${this.displayQuestion(q)}"${this.lang.translate('kb.cannotUndo')}`,
      confirmLabel: this.lang.translate('common.delete'),
    });
    if (!confirmed) return;

    this.deleteQuestionError.set(null);
    this.deletingQuestionIds.update((s) => new Set(s).add(q.id));

    this.suggestedQuestionsService.delete(q.id).subscribe({
      next: () => {
        this.deletingQuestionIds.update((s) => {
          const n = new Set(s);
          n.delete(q.id);
          return n;
        });
        this.refreshSuggestedQuestions();
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.deleteQuestionError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotDeleteQuestion'),
        );
        this.deletingQuestionIds.update((s) => {
          const n = new Set(s);
          n.delete(q.id);
          return n;
        });
      },
    });
  }

  displayQuestion(q: SuggestedQuestion): string {
    return this.lang.lang() === 'ar' ? q.question_ar || q.question : q.question;
  }

  displayAnswer(q: SuggestedQuestion): string {
    return this.lang.lang() === 'ar' ? q.answer_ar || q.answer : q.answer;
  }

  startEditQuestion(q: SuggestedQuestion): void {
    this.editingQuestionId.set(q.id);
    this.editQuestionText.set(this.displayQuestion(q));
    this.editAnswerText.set(this.displayAnswer(q));
    this.editQuestionError.set(null);
  }

  cancelEditQuestion(): void {
    this.editingQuestionId.set(null);
    this.editQuestionText.set('');
    this.editAnswerText.set('');
    this.editQuestionError.set(null);
  }

  saveEditQuestion(q: SuggestedQuestion): void {
    const question = this.editQuestionText().trim();
    const answer = this.editAnswerText().trim();
    if (!question || this.isSavingQuestion()) return;

    this.isSavingQuestion.set(true);
    this.editQuestionError.set(null);

    this.suggestedQuestionsService.update(q.id, question, answer).subscribe({
      next: () => {
        this.isSavingQuestion.set(false);
        this.editingQuestionId.set(null);
        this.editQuestionText.set('');
        this.editAnswerText.set('');
        this.refreshSuggestedQuestions();
      },
      error: (err: HttpErrorResponse) => {
        this.isSavingQuestion.set(false);
        const detail = err.error?.detail;
        this.editQuestionError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotSaveQuestion'),
        );
      },
    });
  }

  statusPillClass(status: string): string {
    switch (status) {
      case 'ready': return 'pill-success';
      case 'processing': return 'pill-warning';
      default: return 'pill-info';
    }
  }

  mediaTypeIcon(mediaType: string): string {
    if (mediaType === 'link') return 'link';
    return mediaType.startsWith('video') ? 'play_circle' : 'image';
  }

  mediaTypeBadge(mediaType: string): string {
    if (mediaType === 'link') return 'link';
    return mediaType.startsWith('video') ? 'video' : 'image';
  }

  linkTypeLabel(linkType: LinkType | undefined): string {
    switch (linkType) {
      case 'youtube': return 'YouTube';
      case 'google_drive': return 'Google Drive';
      default: return this.lang.translate('kb.linkTypeOther');
    }
  }

  youtubeEmbedUrl(url: string | null | undefined): SafeResourceUrl | null {
    if (!url) return null;
    const videoId = extractYoutubeId(url);
    if (!videoId) return null;
    return this.sanitizer.bypassSecurityTrustResourceUrl(
      `https://www.youtube-nocookie.com/embed/${videoId}`,
    );
  }

  private ensureVideoPreview(item: CategoryMediaItem): void {
    if (this.videoPreviewUrls().has(item.id) || this.loadingVideoPreviewIds.has(item.id)) return;
    this.loadingVideoPreviewIds.add(item.id);

    this.mediaService.fetchFile(item.id).subscribe({
      next: (blob) => {
        const objectUrl = URL.createObjectURL(blob);
        this.rawVideoObjectUrls.push(objectUrl);
        const safeUrl = this.sanitizer.bypassSecurityTrustUrl(objectUrl);
        this.videoPreviewUrls.update((m) => {
          const n = new Map(m);
          n.set(item.id, safeUrl);
          return n;
        });
        this.loadingVideoPreviewIds.delete(item.id);
      },
      error: () => {
        this.loadingVideoPreviewIds.delete(item.id);
      },
    });
  }

  private clearVideoPreviews(): void {
    this.rawVideoObjectUrls.forEach((url) => URL.revokeObjectURL(url));
    this.rawVideoObjectUrls.length = 0;
    this.loadingVideoPreviewIds.clear();
    this.videoPreviewUrls.set(new Map());
  }

  private loadCategories(): void {
    this.categoriesService.list().subscribe({
      next: (cats) => this.categories.set(cats),
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.categoriesError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotLoadCategories'),
        );
      },
    });
  }

  private endTogglingPublish(categoryId: string): void {
    this.togglingPublishIds.update((s) => {
      const n = new Set(s);
      n.delete(categoryId);
      return n;
    });
  }

  private setPublishError(categoryId: string, message: string): void {
    this.publishErrors.update((m) => {
      const n = new Map(m);
      n.set(categoryId, message);
      return n;
    });
  }

  private clearPublishError(categoryId: string): void {
    this.publishErrors.update((m) => {
      const n = new Map(m);
      n.delete(categoryId);
      return n;
    });
  }

  private loadContent(categoryId: string): void {
    this.contentLoading.set(true);
    this.contentError.set(null);

    this.categoriesService.getContent(categoryId).subscribe({
      next: (data) => {
        this.content.set(data);
        this.contentLoading.set(false);
        this.filesPage.set(1);
        this.videosPage.set(1);
        this.linksPage.set(1);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.contentError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotLoadContent'),
        );
        this.contentLoading.set(false);
      },
    });
  }

  private refreshContent(): void {
    const cat = this.selectedCategory();
    if (cat) this.loadContent(cat.id);
  }

  private loadSuggestedQuestions(categoryId: string): void {
    this.sqLoading.set(true);
    this.sqError.set(null);

    this.suggestedQuestionsService.list(categoryId).subscribe({
      next: (data) => {
        this.suggestedQuestions.set(data);
        this.sqLoading.set(false);
        this.sqPage.set(1);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.sqError.set(
          typeof detail === 'string' ? detail : this.lang.translate('kb.couldNotLoadSuggestedQuestions'),
        );
        this.sqLoading.set(false);
      },
    });
  }

  private refreshSuggestedQuestions(): void {
    const cat = this.selectedCategory();
    if (cat) this.loadSuggestedQuestions(cat.id);
  }

  private processDocQueue(): void {
    if (this.isDocUploading() || this.docQueue.length === 0) return;

    const file = this.docQueue.shift()!;
    this.docQueueLength.set(this.docQueue.length);
    this.uploadDoc(file);
  }

  private uploadDoc(file: File): void {
    const cat = this.selectedCategory();
    if (!cat) {
      this.processDocQueue();
      return;
    }

    const localId = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

    if (!this.hasExt(file.name, DOC_EXTENSIONS)) {
      this.docUploads.update((list) => [
        {
          localId,
          filename: file.name,
          status: 'error',
          errorMessage: this.lang.translate('kb.unsupportedDocType'),
        },
        ...list,
      ]);
      this.processDocQueue();
      return;
    }

    this.docUploads.update((list) => [
      { localId, filename: file.name, status: 'uploading' },
      ...list,
    ]);
    this.isDocUploading.set(true);

    const linkedMediaId = this.docLinkedMediaId() || undefined;
    const displayName = this.docDisplayName().trim() || undefined;

    this.documentsService.upload(file, cat.id, linkedMediaId, displayName).subscribe({
      next: () => {
        this.docUploads.update((list) => list.filter((i) => i.localId !== localId));
        this.isDocUploading.set(false);
        if (this.docQueue.length === 0) {
          this.docLinkedMediaId.set('');
          this.docDisplayName.set('');
        }
        this.refreshContent();
        this.processDocQueue();
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        const errorMessage =
          typeof detail === 'string' ? detail : this.lang.translate('kb.uploadFailed');
        this.docUploads.update((list) =>
          list.map((i) =>
            i.localId === localId ? { ...i, status: 'error', errorMessage } : i,
          ),
        );
        this.isDocUploading.set(false);
        this.processDocQueue();
      },
    });
  }

  private hasExt(filename: string, exts: string[]): boolean {
    const lower = filename.toLowerCase();
    return exts.some((ext) => lower.endsWith(ext));
  }
}
