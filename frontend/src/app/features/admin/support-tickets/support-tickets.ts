import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  AdminSupportTicket,
  SupportTicketMessage,
  SupportTicketStatus,
} from '../../../core/models/support-ticket.models';
import { LanguageService } from '../../../core/services/language.service';
import { SupportTicketsService } from '../../../core/services/support-tickets.service';

@Component({
  selector: 'app-admin-support-tickets',
  imports: [FormsModule, DatePipe],
  templateUrl: './support-tickets.html',
  styleUrl: './support-tickets.scss',
})
export class AdminSupportTickets implements OnInit {
  private readonly supportTicketsService = inject(SupportTicketsService);
  readonly lang = inject(LanguageService);

  readonly activeTab = signal<SupportTicketStatus>('pending');
  readonly tickets = signal<AdminSupportTicket[]>([]);
  readonly isLoading = signal(true);
  readonly loadError = signal<string | null>(null);

  readonly openTicketId = signal<string | null>(null);
  readonly messages = signal<SupportTicketMessage[]>([]);
  readonly isLoadingMessages = signal(false);
  readonly draftMessage = signal('');
  readonly isSendingMessage = signal(false);
  readonly isResolving = signal(false);
  readonly threadError = signal<string | null>(null);
  readonly deletingTicketId = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
  }

  setActiveTab(tab: SupportTicketStatus): void {
    this.activeTab.set(tab);
    this.openTicketId.set(null);
    this.load();
  }

  openThread(ticket: AdminSupportTicket): void {
    if (this.openTicketId() === ticket.id) {
      this.openTicketId.set(null);
      return;
    }
    this.openTicketId.set(ticket.id);
    this.draftMessage.set('');
    this.threadError.set(null);
    this.loadMessages(ticket.id);
  }

  sendMessage(ticket: AdminSupportTicket): void {
    const content = this.draftMessage().trim();
    if (!content || this.isSendingMessage()) return;

    this.isSendingMessage.set(true);
    this.threadError.set(null);

    this.supportTicketsService.sendAdminMessage(ticket.id, content).subscribe({
      next: () => {
        this.isSendingMessage.set(false);
        this.draftMessage.set('');
        this.loadMessages(ticket.id);
      },
      error: (err: HttpErrorResponse) => {
        this.isSendingMessage.set(false);
        const detail = err.error?.detail;
        this.threadError.set(
          typeof detail === 'string' ? detail : this.lang.translate('supportTicketsAdmin.couldNotSend'),
        );
      },
    });
  }

  resolveTicket(ticket: AdminSupportTicket): void {
    if (this.isResolving()) return;
    this.isResolving.set(true);
    this.threadError.set(null);

    this.supportTicketsService.resolve(ticket.id).subscribe({
      next: () => {
        this.isResolving.set(false);
        this.openTicketId.set(null);
        this.load();
      },
      error: (err: HttpErrorResponse) => {
        this.isResolving.set(false);
        const detail = err.error?.detail;
        this.threadError.set(
          typeof detail === 'string' ? detail : this.lang.translate('supportTicketsAdmin.couldNotResolve'),
        );
      },
    });
  }

  deleteTicket(ticket: AdminSupportTicket, event: Event): void {
    event.stopPropagation();
    if (this.deletingTicketId()) return;
    if (!confirm(this.lang.translate('supportTicketsAdmin.confirmDelete'))) return;

    this.deletingTicketId.set(ticket.id);
    this.supportTicketsService.delete(ticket.id).subscribe({
      next: () => {
        this.deletingTicketId.set(null);
        if (this.openTicketId() === ticket.id) this.openTicketId.set(null);
        this.tickets.update((items) => items.filter((t) => t.id !== ticket.id));
      },
      error: () => {
        this.deletingTicketId.set(null);
      },
    });
  }

  private loadMessages(ticketId: string): void {
    this.isLoadingMessages.set(true);
    this.supportTicketsService.getAdminMessages(ticketId).subscribe({
      next: (messages) => {
        this.messages.set(messages);
        this.isLoadingMessages.set(false);
      },
      error: () => {
        this.isLoadingMessages.set(false);
      },
    });
  }

  private load(): void {
    this.isLoading.set(true);
    this.loadError.set(null);
    this.supportTicketsService.listAll(this.activeTab()).subscribe({
      next: (tickets) => {
        this.tickets.set(tickets);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading.set(false);
        const detail = err.error?.detail;
        this.loadError.set(
          typeof detail === 'string' ? detail : this.lang.translate('supportTicketsAdmin.couldNotLoad'),
        );
      },
    });
  }
}
