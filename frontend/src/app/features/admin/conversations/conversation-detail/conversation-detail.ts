import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { UserConversationsResponse } from '../../../../core/models/conversation.models';
import { ConversationsService } from '../../../../core/services/conversations.service';
import { LanguageService } from '../../../../core/services/language.service';
import { Pagination } from '../../../../shared/pagination/pagination';

const PAGE_SIZE = 10;

@Component({
  selector: 'app-conversation-detail',
  imports: [RouterLink, DatePipe, Pagination],
  templateUrl: './conversation-detail.html',
  styleUrl: './conversation-detail.scss',
})
export class ConversationDetail implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly conversationsService = inject(ConversationsService);
  readonly lang = inject(LanguageService);

  private userId = '';

  readonly data = signal<UserConversationsResponse | null>(null);
  readonly isLoading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly expandedIds = signal<ReadonlySet<string>>(new Set());

  readonly page = signal(1);
  readonly total = signal(0);
  readonly totalPages = signal(1);

  ngOnInit(): void {
    const userId = this.route.snapshot.paramMap.get('userId');
    if (!userId) {
      this.errorMessage.set(this.lang.translate('conversations.couldNotLoadConversations'));
      return;
    }
    this.userId = userId;
    this.load();
  }

  goToPage(page: number): void {
    if (page < 1 || page > this.totalPages() || page === this.page()) return;
    this.page.set(page);
    this.load();
  }

  toggle(conversationId: string): void {
    const next = new Set(this.expandedIds());
    if (next.has(conversationId)) {
      next.delete(conversationId);
    } else {
      next.add(conversationId);
    }
    this.expandedIds.set(next);
  }

  isExpanded(conversationId: string): boolean {
    return this.expandedIds().has(conversationId);
  }

  private load(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);

    this.conversationsService.getUserConversations(this.userId, this.page(), PAGE_SIZE).subscribe({
      next: (res) => {
        this.data.set(res);
        this.total.set(res.total);
        this.totalPages.set(Math.max(1, res.total_pages));
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.errorMessage.set(
          typeof detail === 'string' ? detail : this.lang.translate('conversations.couldNotLoadConversations'),
        );
        this.isLoading.set(false);
      },
    });
  }
}
