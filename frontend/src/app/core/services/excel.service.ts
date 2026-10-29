import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ExcelRow, ExcelTable } from '../models/excel.models';

@Injectable({ providedIn: 'root' })
export class ExcelService {
  constructor(private readonly http: HttpClient) {}

  getTable(documentId: string): Observable<ExcelTable> {
    return this.http.get<ExcelTable>(`${environment.apiBaseUrl}/documents/${documentId}/excel`);
  }

  addRow(documentId: string, rowData: Record<string, string>): Observable<ExcelRow> {
    return this.http.post<ExcelRow>(
      `${environment.apiBaseUrl}/documents/${documentId}/excel/rows`,
      { row_data: rowData },
    );
  }

  updateRow(rowId: string, rowData: Record<string, string>): Observable<ExcelRow> {
    return this.http.put<ExcelRow>(
      `${environment.apiBaseUrl}/excel-rows/${rowId}`,
      { row_data: rowData },
    );
  }

  deleteRow(rowId: string): Observable<void> {
    return this.http.delete<void>(`${environment.apiBaseUrl}/excel-rows/${rowId}`);
  }
}
