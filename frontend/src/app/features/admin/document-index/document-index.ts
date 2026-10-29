import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Subject, catchError, debounceTime, distinctUntilChanged, merge, of, switchMap } from 'rxjs';
import { DocumentIndexPage, DocumentIndexSearchResult } from '../../../core/models/document-index.models';
import { DocumentIndexService } from '../../../core/services/document-index.service';
import { LanguageService } from '../../../core/services/language.service';

@Component({
  selector: 'app-document-index',
  imports: [FormsModule],
  templateUrl: './document-index.html',
  styleUrl: './document-index.scss',
})
export class DocumentIndex {
  private readonly documentIndexService = inject(DocumentIndexService);
  readonly lang = inject(LanguageService);

  readonly query = signal('');
  readonly results = signal<DocumentIndexSearchResult[]>([]);
  readonly hasSearched = signal(false);
  readonly isSearching = signal(false);
  readonly searchError = signal<string | null>(null);

  readonly isModalOpen = signal(false);
  readonly selectedPage = signal<DocumentIndexPage | null>(null);
  readonly isLoadingPage = signal(false);
  readonly pageError = signal<string | null>(null);

  // Every keystroke (onQueryInput) goes through this and gets debounced;
  // an explicit trigger — the Search button, or the field being cleared —
  // goes through this untouched, so it fires immediately instead of waiting
  // out the debounce window. Both feed the same switchMap so an in-flight
  // request from either source is cancelled the moment a newer one starts;
  // without that, a slow response to an earlier keystroke could land after
  // a later one and show stale results.
  private readonly debouncedQuery = new Subject<string>();
  private readonly immediateQuery = new Subject<string>();

  constructor() {
    merge(this.debouncedQuery.pipe(debounceTime(300), distinctUntilChanged()), this.immediateQuery)
      .pipe(
        switchMap((rawQuery) => {
          const q = rawQuery.trim();
          if (!q) {
            this.isSearching.set(false);
            this.searchError.set(null);
            this.hasSearched.set(false);
            this.results.set([]);
            return of(null);
          }

          this.isSearching.set(true);
          this.searchError.set(null);
          this.hasSearched.set(true);

          return this.documentIndexService.search(q).pipe(
            catchError((err: HttpErrorResponse) => {
              const detail = err.error?.detail;
              this.searchError.set(
                typeof detail === 'string' ? detail : this.lang.translate('documentIndex.searchError'),
              );
              this.results.set([]);
              this.isSearching.set(false);
              return of(null);
            }),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((results) => {
        if (results === null) return;
        this.results.set(results);
        this.isSearching.set(false);
      });
  }

  onQueryInput(value: string): void {
    this.query.set(value);
    if (!value.trim()) {
      // Clearing the field should clear results (and cancel any in-flight
      // request for the text that was just erased) right away, not after
      // the usual debounce delay.
      this.immediateQuery.next(value);
    } else {
      this.debouncedQuery.next(value);
    }
  }

  /** Search button / form submit — bypasses the debounce for an immediate search. */
  search(): void {
    this.immediateQuery.next(this.query());
  }

  openResult(result: DocumentIndexSearchResult): void {
    this.isModalOpen.set(true);
    this.isLoadingPage.set(true);
    this.pageError.set(null);
    this.selectedPage.set(null);

    this.documentIndexService.getPage(result.page_id).subscribe({
      next: (page) => {
        this.selectedPage.set(page);
        this.isLoadingPage.set(false);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.pageError.set(
          typeof detail === 'string' ? detail : this.lang.translate('documentIndex.pageLoadError'),
        );
        this.isLoadingPage.set(false);
      },
    });
  }

  closeModal(): void {
    if (this.isLoadingPage()) return;
    this.isModalOpen.set(false);
    this.selectedPage.set(null);
    this.pageError.set(null);
  }

  pageLabel(result: { file_type: string; page_number: number }): string {
    const key = result.file_type === 'pptx' ? 'documentIndex.slide' : 'documentIndex.page';
    return `${this.lang.translate(key)} ${result.page_number}`;
  }
}
