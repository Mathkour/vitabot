import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { DocumentListItem, DocumentUploadResponse } from '../models/document.models';

@Injectable({ providedIn: 'root' })
export class DocumentsService {
  constructor(private readonly http: HttpClient) {}

  upload(
    file: File,
    categoryId: string,
    linkedMediaId?: string,
    displayName?: string,
  ): Observable<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category_id', categoryId);
    if (linkedMediaId) formData.append('linked_media_id', linkedMediaId);
    if (displayName) formData.append('display_name', displayName);
    return this.http.post<DocumentUploadResponse>(
      `${environment.apiBaseUrl}/documents/upload`,
      formData
    );
  }

  list(): Observable<DocumentListItem[]> {
    return this.http.get<DocumentListItem[]>(`${environment.apiBaseUrl}/documents`);
  }

  delete(documentId: string): Observable<void> {
    return this.http.delete<void>(`${environment.apiBaseUrl}/documents/${documentId}`);
  }

  rename(documentId: string, displayName: string): Observable<void> {
    return this.http.patch<void>(`${environment.apiBaseUrl}/documents/${documentId}/name`, {
      display_name: displayName,
    });
  }

  getFileUrl(documentId: string): string {
    return `${environment.apiBaseUrl}/documents/file/${documentId}`;
  }

  /**
   * Downloads a document to the user's device (browser "Save As" behavior)
   * instead of opening it in a new tab or an external viewer. onError is
   * called (instead of only logging to the console) when the file can't be
   * fetched — e.g. its backing file_path row survived but the file itself is
   * gone (local-disk uploads don't survive a Render redeploy/restart unless
   * Cloudinary is configured — see services/storage.py), which otherwise
   * looks to the user like the download button silently does nothing.
   */
  downloadFile(documentId: string, filename: string, onError?: (err: HttpErrorResponse) => void): void {
    const fileUrl = this.getFileUrl(documentId);

    this.http.get(fileUrl, { responseType: 'blob' }).subscribe({
      next: (blob) => {
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = objectUrl;
        anchor.download = filename;
        anchor.click();
        URL.revokeObjectURL(objectUrl);
      },
      error: (err: HttpErrorResponse) => {
        console.error(`Could not download document ${documentId}:`, err);
        onError?.(err);
      },
    });
  }
}
