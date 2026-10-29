import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CreateTenantRequest, CreateTenantResponse, SuperadminTenant } from '../models/superadmin.models';

@Injectable({ providedIn: 'root' })
export class SuperadminService {
  constructor(private readonly http: HttpClient) {}

  listTenants(): Observable<SuperadminTenant[]> {
    return this.http.get<SuperadminTenant[]>(`${environment.apiBaseUrl}/admin/tenants`);
  }

  createTenant(payload: CreateTenantRequest): Observable<CreateTenantResponse> {
    return this.http.post<CreateTenantResponse>(`${environment.apiBaseUrl}/admin/tenants`, payload);
  }
}
