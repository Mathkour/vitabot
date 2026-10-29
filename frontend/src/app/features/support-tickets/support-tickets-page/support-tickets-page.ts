import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { LanguageService } from '../../../core/services/language.service';
import { SupportTicketsService } from '../../../core/services/support-tickets.service';
import { SupportTicket, SupportTicketMessage } from '../../../core/models/support-ticket.models';

@Component({
  selector: 'app-support-tickets-page',
  imports: [FormsModule],
  templateUrl: './support-tickets-page.html',
  styleUrl: './support-tickets-page.scss',
})
export class SupportTicketsPage implements OnInit {
  private readonly supportTicketsService = inject(SupportTicketsService);
  private readonly route = inject(ActivatedRoute);
  readonly lang = inject(LanguageService);

  readonly tickets = signal<SupportTicket[]>([]);
  readonly isLoading = signal(true);
  readonly errorMessage = signal<string | null>(null);

  readonly expandedTicketId = signal<string | null>(null);
  readonly messages = signal<SupportTicketMessage[]>([]);
  readonly isLoadingMessages = signal(false);
  readonly draftMessage = signal('');
  readonly isSendingMessage = signal(false);
  readonly sendError = signal<string | null>(null);

  ngOnInit(): void {
    const requestedTicketId = this.route.snapshot.queryParamMap.get('ticketId');
    this.supportTicketsService.listMine().subscribe({
      next: (tickets) => {
        this.tickets.set(tickets);
        this.isLoading.set(false);
        const requested = requestedTicketId && tickets.find((t) => t.id === requestedTicketId);
        if (requested) {
          this.toggleTicket(requested);
        }
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading.set(false);
        const detail = err.error?.detail;
        this.errorMessage.set(
          typeof detail === 'string' ? detail : this.lang.translate('supportTicket.couldNotLoad'),
        );
      },
    });
  }

  toggleTicket(ticket: SupportTicket): void {
    if (this.expandedTicketId() === ticket.id) {
      this.expandedTicketId.set(null);
      return;
    }
    this.expandedTicketId.set(ticket.id);
    this.draftMessage.set('');
    this.sendError.set(null);
    this.loadMessages(ticket.id);
  }

  sendMessage(ticket: SupportTicket): void {
    const content = this.draftMessage().trim();
    if (!content || this.isSendingMessage()) return;

    this.isSendingMessage.set(true);
    this.sendError.set(null);

    this.supportTicketsService.sendMessage(ticket.id, content).subscribe({
      next: () => {
        this.isSendingMessage.set(false);
        this.draftMessage.set('');
        this.loadMessages(ticket.id);
      },
      error: (err: HttpErrorResponse) => {
        this.isSendingMessage.set(false);
        const detail = err.error?.detail;
        this.sendError.set(
          typeof detail === 'string' ? detail : this.lang.translate('supportTicket.couldNotSend'),
        );
      },
    });
  }

  private loadMessages(ticketId: string): void {
    this.isLoadingMessages.set(true);
    this.messages.set([]);
    this.supportTicketsService.getMessages(ticketId).subscribe({
      next: (messages) => {
        this.messages.set(messages);
        this.isLoadingMessages.set(false);
      },
      error: () => {
        this.isLoadingMessages.set(false);
      },
    });
  }
}
