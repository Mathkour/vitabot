import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Category, CategoryContent } from '../models/category.models';

@Injectable({ providedIn: 'root' })
export class CategoriesService {
  constructor(private readonly http: HttpClient) {}

  list(): Observable<Category[]> {
    return this.http.get<Category[]>(`${environment.apiBaseUrl}/categories`);
  }

  listPublished(): Observable<Category[]> {
    return this.http.get<Category[]>(`${environment.apiBaseUrl}/categories/published`);
  }

  create(name: string): Observable<Category> {
    return this.http.post<Category>(`${environment.apiBaseUrl}/categories`, { name });
  }

  getContent(categoryId: string): Observable<CategoryContent> {
    return this.http.get<CategoryContent>(`${environment.apiBaseUrl}/categories/${categoryId}/content`);
  }

  publish(categoryId: string): Observable<void> {
    return this.http.post<void>(`${environment.apiBaseUrl}/categories/${categoryId}/publish`, {});
  }

  unpublish(categoryId: string): Observable<void> {
    return this.http.post<void>(`${environment.apiBaseUrl}/categories/${categoryId}/unpublish`, {});
  }

  delete(categoryId: string): Observable<void> {
    return this.http.delete<void>(`${environment.apiBaseUrl}/categories/${categoryId}`);
  }
}
