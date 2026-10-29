import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { FaqCategorySummary, FaqGroupPage, FaqItem } from '../models/faq.models';

@Injectable({ providedIn: 'root' })
export class FaqService {
  constructor(private readonly http: HttpClient) {}

  /** Admin's full FAQ list (every item, categorized or not). */
  list(): Observable<FaqItem[]> {
    return this.http.get<FaqItem[]>(`${environment.apiBaseUrl}/faq`);
  }

  /** Admin's "uncategorized" filter, so categorization backlog is easy to find. */
  listUncategorized(): Observable<FaqItem[]> {
    return this.http.get<FaqItem[]>(`${environment.apiBaseUrl}/admin/faqs`, {
      params: { uncategorized: 'true' },
    });
  }

  /** Member-facing accordion headers: one lightweight summary (name + total
   * count) per non-empty category — no FAQ text, so this is cheap even with
   * many categories. */
  listGroupedSummary(): Observable<FaqCategorySummary[]> {
    return this.http.get<FaqCategorySummary[]>(`${environment.apiBaseUrl}/faq/grouped`);
  }

  /** One category's FAQs, paginated — fetched lazily when that category's
   * accordion section is opened (and again when the member pages within it). */
  listCategoryPage(categoryId: string, page: number, pageSize = 10): Observable<FaqGroupPage> {
    return this.http.get<FaqGroupPage>(`${environment.apiBaseUrl}/faq/grouped`, {
      params: { category_id: categoryId, page, page_size: pageSize },
    });
  }

  /** Every categorized FAQ, flat and unpaginated — fetched lazily only once
   * the member starts typing into search, to power client-side fuzzy search
   * without GET /faq/grouped having to bulk-load everything up front. */
  searchCorpus(): Observable<FaqItem[]> {
    return this.http.get<FaqItem[]>(`${environment.apiBaseUrl}/faq/search-corpus`);
  }

  /** FAQ items merged with Error Solutions — Vita Care tenant only (backend-enforced). */
  listCombined(): Observable<FaqItem[]> {
    return this.http.get<FaqItem[]>(`${environment.apiBaseUrl}/faq/combined`);
  }

  create(
    question: string,
    answer: string,
    categoryId: string | null,
    questionAr?: string,
    answerAr?: string,
  ): Observable<FaqItem> {
    return this.http.post<FaqItem>(`${environment.apiBaseUrl}/faq`, {
      question,
      answer,
      question_ar: questionAr || null,
      answer_ar: answerAr || null,
      category_id: categoryId,
    });
  }

  update(
    id: string,
    question: string,
    answer: string,
    categoryId: string | null,
    questionAr?: string,
    answerAr?: string,
  ): Observable<FaqItem> {
    return this.http.put<FaqItem>(`${environment.apiBaseUrl}/faq/${id}`, {
      question,
      answer,
      question_ar: questionAr || null,
      answer_ar: answerAr || null,
      category_id: categoryId,
    });
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${environment.apiBaseUrl}/faq/${id}`);
  }
}
