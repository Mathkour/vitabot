import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { MyConversationsResponse, UserConversationsResponse } from '../models/conversation.models';

@Injectable({ providedIn: 'root' })
export class ConversationsService {
  constructor(private readonly http: HttpClient) {}

  getUserConversations(
    userId: string,
    page = 1,
    pageSize = 20,
  ): Observable<UserConversationsResponse> {
    return this.http.get<UserConversationsResponse>(
      `${environment.apiBaseUrl}/admin/users/${userId}/conversations`,
      { params: { page, page_size: pageSize } },
    );
  }

  getMyConversations(): Observable<MyConversationsResponse> {
    return this.http.get<MyConversationsResponse>(`${environment.apiBaseUrl}/conversations/me`);
  }
}
