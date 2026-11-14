import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  CompanyUser,
  CreateUserRequest,
  ImportConfirmRequest,
  ImportConfirmResponse,
  ImportPreviewResponse,
  UpdateUserRequest,
  UsersListParams,
  UsersListResponse,
} from '../models/user.models';

@Injectable({ providedIn: 'root' })
export class UsersService {
  constructor(private readonly http: HttpClient) {}

  list(params: UsersListParams = {}): Observable<UsersListResponse> {
    let httpParams = new HttpParams();
    if (params.search) httpParams = httpParams.set('search', params.search);
    if (params.page) httpParams = httpParams.set('page', params.page);
    if (params.page_size) httpParams = httpParams.set('page_size', params.page_size);
    if (params.company_id) httpParams = httpParams.set('company_id', params.company_id);

    return this.http.get<UsersListResponse>(`${environment.apiBaseUrl}/users`, {
      params: httpParams,
    });
  }

  create(payload: CreateUserRequest): Observable<CompanyUser> {
    return this.http.post<CompanyUser>(`${environment.apiBaseUrl}/users/create`, payload);
  }

  update(userId: string, payload: UpdateUserRequest): Observable<{ status: string }> {
    return this.http.patch<{ status: string }>(`${environment.apiBaseUrl}/users/${userId}`, payload);
  }

  delete(userId: string): Observable<{ status: string }> {
    return this.http.delete<{ status: string }>(`${environment.apiBaseUrl}/users/${userId}`);
  }

  /** Admin sets a new password; the user is signed out everywhere. */
  resetPassword(userId: string, password: string): Observable<{ status: string; signed_out: boolean }> {
    return this.http.post<{ status: string; signed_out: boolean }>(
      `${environment.apiBaseUrl}/users/${userId}/password`,
      { password },
    );
  }

  importPreview(file: File): Observable<ImportPreviewResponse> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<ImportPreviewResponse>(
      `${environment.apiBaseUrl}/users/import/preview`,
      formData,
    );
  }

  importConfirm(payload: ImportConfirmRequest): Observable<ImportConfirmResponse> {
    return this.http.post<ImportConfirmResponse>(
      `${environment.apiBaseUrl}/users/import/confirm`,
      payload,
    );
  }
}
