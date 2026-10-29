import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { VideoItem } from '../models/video.models';

@Injectable({ providedIn: 'root' })
export class VideosService {
  constructor(private readonly http: HttpClient) {}

  /** Admin-uploaded YouTube videos — Vita Care only (backend-enforced). */
  list(): Observable<VideoItem[]> {
    return this.http.get<VideoItem[]>(`${environment.apiBaseUrl}/videos`);
  }
}
