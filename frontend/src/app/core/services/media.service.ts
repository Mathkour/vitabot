import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { skipLoadingIndicator } from '../interceptors/loading-indicator.interceptor';
import { LinkType } from '../models/category.models';
import { MediaLinkResponse, MediaUploadResponse } from '../models/media.models';

@Injectable({ providedIn: 'root' })
export class MediaService {
  constructor(private readonly http: HttpClient) {}

  upload(
    file: File,
    description: string,
    categoryId?: string,
    displayName?: string,
  ): Observable<MediaUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('description', description);
    if (categoryId) formData.append('category_id', categoryId);
    if (displayName) formData.append('display_name', displayName);
    return this.http.post<MediaUploadResponse>(
      `${environment.apiBaseUrl}/media/upload`,
      formData
    );
  }

  addLink(
    url: string,
    description: string,
    categoryId: string,
    linkType: LinkType = 'other',
    displayName?: string,
  ): Observable<MediaLinkResponse> {
    return this.http.post<MediaLinkResponse>(`${environment.apiBaseUrl}/media/link`, {
      url,
      description,
      category_id: categoryId,
      link_type: linkType,
      display_name: displayName || undefined,
    });
  }

  delete(mediaId: string): Observable<void> {
    return this.http.delete<void>(`${environment.apiBaseUrl}/media/${mediaId}`);
  }

  rename(mediaId: string, displayName: string): Observable<void> {
    return this.http.patch<void>(`${environment.apiBaseUrl}/media/${mediaId}/name`, {
      display_name: displayName,
    });
  }

  getFileUrl(mediaId: string): string {
    return `${environment.apiBaseUrl}/media/file/${mediaId}`;
  }

  /** Used for silent background thumbnail previews — kept off the global loading bar. */
  fetchFile(mediaId: string): Observable<Blob> {
    return this.http.get(this.getFileUrl(mediaId), {
      responseType: 'blob',
      context: skipLoadingIndicator(),
    });
  }
}
