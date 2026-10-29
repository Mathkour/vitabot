import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ErrorSolutionImportResponse, ErrorSolutionItem } from '../models/error-solution.models';

@Injectable({ providedIn: 'root' })
export class ErrorSolutionsService {
  constructor(private readonly http: HttpClient) {}

  list(): Observable<ErrorSolutionItem[]> {
    return this.http.get<ErrorSolutionItem[]>(`${environment.apiBaseUrl}/error-solutions`);
  }

  /** Error Solutions with no category assigned yet, so the admin can triage them. */
  listUncategorized(): Observable<ErrorSolutionItem[]> {
    return this.http.get<ErrorSolutionItem[]>(`${environment.apiBaseUrl}/admin/error-solutions`, {
      params: { uncategorized: 'true' },
    });
  }

  create(errorText: string, solutionText: string, categoryId: string | null): Observable<ErrorSolutionItem> {
    return this.http.post<ErrorSolutionItem>(`${environment.apiBaseUrl}/error-solutions`, {
      error_text: errorText,
      solution_text: solutionText,
      category_id: categoryId,
    });
  }

  update(
    id: string,
    errorText: string,
    solutionText: string,
    categoryId: string | null,
  ): Observable<ErrorSolutionItem> {
    return this.http.put<ErrorSolutionItem>(`${environment.apiBaseUrl}/error-solutions/${id}`, {
      error_text: errorText,
      solution_text: solutionText,
      category_id: categoryId,
    });
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${environment.apiBaseUrl}/error-solutions/${id}`);
  }

  importExcel(file: File): Observable<ErrorSolutionImportResponse> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<ErrorSolutionImportResponse>(
      `${environment.apiBaseUrl}/error-solutions/import-excel`,
      formData,
    );
  }
}
