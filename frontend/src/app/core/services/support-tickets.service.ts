import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { skipLoadingIndicator } from '../interceptors/loading-indicator.interceptor';
import {
  AdminSupportTicket,
  SupportTicket,
  SupportTicketMessage,
  SupportTicketStatus,
  UnseenSupportTicket,
} from '../models/support-ticket.models';

@Injectable({ providedIn: 'root' })
export class SupportTicketsService {
  constructor(private readonly http: HttpClient) {}

  create(question: string, conversationId: string | null): Observable<SupportTicket> {
    return this.http.post<SupportTicket>(`${environment.apiBaseUrl}/support-tickets`, {
      question,
      conversation_id: conversationId,
    });
  }

  listMine(): Observable<SupportTicket[]> {
    return this.http.get<SupportTicket[]>(`${environment.apiBaseUrl}/support-tickets/me`);
  }

  myUnseenCount(): Observable<{ count: number }> {
    return this.http.get<{ count: number }>(`${environment.apiBaseUrl}/support-tickets/me/unseen-count`, {
      context: skipLoadingIndicator(),
    });
  }

  myUnseenTickets(): Observable<UnseenSupportTicket[]> {
    return this.http.get<UnseenSupportTicket[]>(`${environment.apiBaseUrl}/support-tickets/me/unseen`, {
      context: skipLoadingIndicator(),
    });
  }

  /** Also marks the thread as read (clears the unseen badge for this ticket). */
  getMessages(ticketId: string): Observable<SupportTicketMessage[]> {
    return this.http.get<SupportTicketMessage[]>(`${environment.apiBaseUrl}/support-tickets/${ticketId}/messages`);
  }

  /** User sends a follow-up message on their own ticket. Rejected once the ticket is resolved. */
  sendMessage(ticketId: string, content: string): Observable<SupportTicketMessage> {
    return this.http.post<SupportTicketMessage>(
      `${environment.apiBaseUrl}/support-tickets/${ticketId}/messages/me`,
      { content },
    );
  }

  listAll(status?: SupportTicketStatus): Observable<AdminSupportTicket[]> {
    return this.http.get<AdminSupportTicket[]>(`${environment.apiBaseUrl}/support-tickets`, {
      params: status ? { status } : {},
    });
  }

  pendingCount(): Observable<{ count: number }> {
    return this.http.get<{ count: number }>(`${environment.apiBaseUrl}/support-tickets/pending-count`, {
      context: skipLoadingIndicator(),
    });
  }

  getAdminMessages(ticketId: string): Observable<SupportTicketMessage[]> {
    return this.http.get<SupportTicketMessage[]>(
      `${environment.apiBaseUrl}/support-tickets/${ticketId}/admin-messages`,
    );
  }

  sendAdminMessage(ticketId: string, content: string): Observable<SupportTicketMessage> {
    return this.http.post<SupportTicketMessage>(`${environment.apiBaseUrl}/support-tickets/${ticketId}/messages`, {
      content,
    });
  }

  resolve(ticketId: string): Observable<void> {
    return this.http.post<void>(`${environment.apiBaseUrl}/support-tickets/${ticketId}/resolve`, {});
  }

  delete(ticketId: string): Observable<void> {
    return this.http.delete<void>(`${environment.apiBaseUrl}/support-tickets/${ticketId}`);
  }
}
