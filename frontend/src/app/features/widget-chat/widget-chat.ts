import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, ViewChild, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { ChatService } from '../../core/services/chat.service';
import { LanguageService } from '../../core/services/language.service';
import { WidgetConfig, WidgetSessionService } from '../../core/services/widget-session.service';

interface WidgetMessage {
  id: number;
  role: 'user' | 'bot';
  text: string;
}

type Phase = 'connecting' | 'ready' | 'failed';

/**
 * Minimal chat-only view rendered inside the embeddable widget's iframe.
 * Params arrive in the URL fragment (#tenant=..&token=..&lang=..) so the
 * partner JWT never reaches a server log or a Referer header; the fragment
 * is stripped from the address bar as soon as it has been read.
 */
@Component({
  selector: 'app-widget-chat',
  imports: [FormsModule],
  templateUrl: './widget-chat.html',
  styleUrl: './widget-chat.scss',
})
export class WidgetChat {
  private readonly session = inject(WidgetSessionService);
  private readonly chatService = inject(ChatService);
  readonly lang = inject(LanguageService);

  @ViewChild('scrollContainer') private scrollContainer?: ElementRef<HTMLDivElement>;

  private conversationId: string | null = null;
  private nextId = 1;

  readonly phase = signal<Phase>('connecting');
  readonly config = signal<WidgetConfig | null>(null);
  readonly messages = signal<WidgetMessage[]>([]);
  readonly draft = signal('');
  readonly isLoading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly sessionExpired = signal(false);

  readonly botName = computed(() => this.config()?.bot_name ?? '');
  readonly accent = computed(() => this.config()?.icon_color ?? '#2563EB');
  readonly suggestedQuestions = computed(() => this.config()?.suggested_questions ?? []);
  readonly showEmptyState = computed(() => this.messages().length === 0);

  constructor() {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    const tenant = params.get('tenant');
    const token = params.get('token');
    const lang = params.get('lang');
    history.replaceState(null, '', window.location.pathname);

    if (lang === 'ar' || lang === 'en') {
      this.lang.lang.set(lang);
      document.documentElement.setAttribute('lang', lang);
      document.documentElement.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
    }

    if (!tenant || !token) {
      this.phase.set('failed');
      return;
    }

    this.session.loadConfig(tenant).subscribe({ next: (c) => this.config.set(c), error: () => {} });
    this.session.verify(tenant, token).subscribe({
      next: () => this.phase.set('ready'),
      error: () => this.phase.set('failed'),
    });
  }

  send(): void {
    const question = this.draft().trim();
    if (!question || this.isLoading() || this.phase() !== 'ready') return;

    this.messages.update((m) => [...m, { id: this.nextId++, role: 'user', text: question }]);
    this.draft.set('');
    this.errorMessage.set(null);
    this.isLoading.set(true);
    this.scrollToBottom();

    this.chatService
      .ask({ question, conversation_id: this.conversationId })
      .pipe(finalize(() => this.isLoading.set(false)))
      .subscribe({
        next: (res) => {
          if (!res) {
            this.errorMessage.set(this.lang.translate('common.noResponse'));
          } else {
            this.conversationId = res.conversation_id;
            this.messages.update((m) => [...m, { id: this.nextId++, role: 'bot', text: res.answer }]);
          }
          this.scrollToBottom();
        },
        error: (err: HttpErrorResponse) => {
          if (err.status === 401) {
            this.sessionExpired.set(true);
            this.session.clear();
            // Ask the host-side widget to reload us with a fresh partner token.
            window.parent.postMessage({ type: 'cpbot:session-expired' }, '*');
          } else {
            const detail = err.error?.detail;
            this.errorMessage.set(
              typeof detail === 'string' ? detail : this.lang.translate('common.somethingWrong'),
            );
          }
          this.scrollToBottom();
        },
      });
  }

  selectSuggestedQuestion(question: string): void {
    this.draft.set(question);
    this.send();
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  closeWidget(): void {
    window.parent.postMessage({ type: 'cpbot:close' }, '*');
  }

  private scrollToBottom(): void {
    queueMicrotask(() => {
      const el = this.scrollContainer?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }
}
