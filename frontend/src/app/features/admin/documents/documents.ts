import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Category } from '../../../core/models/category.models';
import { DocumentListItem } from '../../../core/models/document.models';
import { CategoriesService } from '../../../core/services/categories.service';
import { DocumentsService } from '../../../core/services/documents.service';

type UploadStatus = 'uploading' | 'error';

interface UploadItem {
  id: string;
  filename: string;
  status: UploadStatus;
  errorMessage?: string;
}

const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.xlsx'];

@Component({
  selector: 'app-documents',
  imports: [FormsModule],
  templateUrl: './documents.html',
  styleUrl: './documents.scss',
})
export class Documents implements OnInit {
  private readonly documentsService = inject(DocumentsService);
  private readonly categoriesService = inject(CategoriesService);

  readonly uploads = signal<UploadItem[]>([]);
  readonly documents = signal<DocumentListItem[]>([]);
  readonly loadError = signal<string | null>(null);
  readonly deleteError = signal<string | null>(null);
  readonly deletingIds = signal<Set<string>>(new Set());

  readonly categories = signal<Category[]>([]);
  readonly categoriesLoadError = signal<string | null>(null);
  readonly selectedCategoryId = signal('');

  ngOnInit(): void {
    this.loadDocuments();
    this.loadCategories();
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = input.files;
    if (!files) return;

    for (const file of Array.from(files)) {
      this.handleFile(file);
    }

    input.value = '';
  }

  deleteDocument(doc: DocumentListItem): void {
    if (!confirm('Are you sure you want to delete this file?')) return;

    this.deleteError.set(null);
    this.deletingIds.update((ids) => new Set(ids).add(doc.id));

    this.documentsService.delete(doc.id).subscribe({
      next: () => {
        this.documents.update((items) => items.filter((item) => item.id !== doc.id));
        this.deletingIds.update((ids) => {
          const next = new Set(ids);
          next.delete(doc.id);
          return next;
        });
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.deleteError.set(typeof detail === 'string' ? detail : 'Could not delete this file.');
        this.deletingIds.update((ids) => {
          const next = new Set(ids);
          next.delete(doc.id);
          return next;
        });
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

  private loadDocuments(): void {
    this.documentsService.list().subscribe({
      next: (docs) => {
        this.documents.set(docs);
        this.loadError.set(null);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.loadError.set(typeof detail === 'string' ? detail : 'Could not load documents.');
      },
    });
  }

  private loadCategories(): void {
    this.categoriesService.list().subscribe({
      next: (cats) => {
        this.categories.set(cats);
        this.categoriesLoadError.set(null);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.categoriesLoadError.set(
          typeof detail === 'string' ? detail : 'Could not load categories.'
        );
      },
    });
  }

  private handleFile(file: File): void {
    const categoryId = this.selectedCategoryId();
    if (!categoryId) return;

    const id = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

    if (!this.hasAllowedExtension(file.name)) {
      this.uploads.update((items) => [
        {
          id,
          filename: file.name,
          status: 'error',
          errorMessage: 'Unsupported file type. Only PDF, Word (.docx) and Excel (.xlsx) files are allowed.',
        },
        ...items,
      ]);
      return;
    }

    this.uploads.update((items) => [{ id, filename: file.name, status: 'uploading' }, ...items]);

    this.documentsService.upload(file, categoryId).subscribe({
      next: () => {
        this.uploads.update((items) => items.filter((item) => item.id !== id));
        this.loadDocuments();
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        const message = typeof detail === 'string' ? detail : 'Upload failed. Please try again.';
        this.uploads.update((items) =>
          items.map((item) =>
            item.id === id ? { ...item, status: 'error', errorMessage: message } : item
          )
        );
      },
    });
  }

  private hasAllowedExtension(filename: string): boolean {
    const lower = filename.toLowerCase();
    return ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext));
  }
}
