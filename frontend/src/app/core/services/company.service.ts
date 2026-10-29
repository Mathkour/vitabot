import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Company, CompanyRequest } from '../models/company.models';

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
}
