import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  Company,
  CompanyOdooRequest,
  CompanyOdooSettings,
  CompanyRequest,
  OdooTestResult,
} from '../models/company.models';

@Injectable({ providedIn: 'root' })
export class CompanyService {
  constructor(private readonly http: HttpClient) {}

  list(): Observable<Company[]> {
    return this.http.get<Company[]>(`${environment.apiBaseUrl}/companies`);
  }

  create(payload: CompanyRequest): Observable<Company> {
    return this.http.post<Company>(`${environment.apiBaseUrl}/companies`, payload);
  }

  rename(companyId: string, payload: CompanyRequest): Observable<{ status: string }> {
    return this.http.patch<{ status: string }>(`${environment.apiBaseUrl}/companies/${companyId}`, payload);
  }

  delete(companyId: string): Observable<{ status: string }> {
    return this.http.delete<{ status: string }>(`${environment.apiBaseUrl}/companies/${companyId}`);
  }

  getOdoo(companyId: string): Observable<CompanyOdooSettings> {
    return this.http.get<CompanyOdooSettings>(`${environment.apiBaseUrl}/companies/${companyId}/odoo`);
  }

  saveOdoo(companyId: string, payload: CompanyOdooRequest): Observable<CompanyOdooSettings> {
    return this.http.put<CompanyOdooSettings>(`${environment.apiBaseUrl}/companies/${companyId}/odoo`, payload);
  }

  /** Tries the login without saving; blank fields fall back to what's saved. */
  testOdoo(companyId: string, payload: CompanyOdooRequest): Observable<OdooTestResult> {
    return this.http.post<OdooTestResult>(`${environment.apiBaseUrl}/companies/${companyId}/odoo/test`, payload);
  }
}
