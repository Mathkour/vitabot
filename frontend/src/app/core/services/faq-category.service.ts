import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { FaqCategory } from '../models/faq.models';

@Injectable({ providedIn: 'root' })
export class FaqCategoryService {
  constructor(private readonly http: HttpClient) {}

  list(): Observable<FaqCategory[]> {
    return this.http.get<FaqCategory[]>(`${environment.apiBaseUrl}/admin/faq-categories`);
  }

  create(nameAr: string, nameEn: string, displayOrder: number | null): Observable<FaqCategory> {
    return this.http.post<FaqCategory>(`${environment.apiBaseUrl}/admin/faq-categories`, {
      name_ar: nameAr,
      name_en: nameEn,
      display_order: displayOrder,
    });
  }

  update(id: string, nameAr: string, nameEn: string, displayOrder: number | null): Observable<FaqCategory> {
    return this.http.put<FaqCategory>(`${environment.apiBaseUrl}/admin/faq-categories/${id}`, {
      name_ar: nameAr,
      name_en: nameEn,
      display_order: displayOrder,
    });
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${environment.apiBaseUrl}/admin/faq-categories/${id}`);
  }
}
