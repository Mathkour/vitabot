import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { LanguageService } from '../../../core/services/language.service';
import { OdooService } from '../../../core/services/odoo.service';
import { SuperadminNav } from '../superadmin-nav/superadmin-nav';

interface OdooChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
}

@Component({
  selector: 'app-odoo-chat',
  imports: [FormsModule, SuperadminNav],
  templateUrl: './odoo-chat.html',
  styleUrl: './odoo-chat.scss',
})
export class OdooChat {
  private readonly odooService = inject(OdooService);
  readonly lang = inject(LanguageService);

  @ViewChild('scrollContainer') private scrollContainer?: ElementRef<HTMLDivElement>;

  readonly messages = signal<OdooChatMessage[]>([]);
  readonly draft = signal('');
  readonly isLoading = signal(false);
  readonly errorMessage = signal<string | null>(null);

  send(): void {
    const question = this.draft().trim();
    if (!question || this.isLoading()) return;

    this.messages.update((items) => [
      ...items,
      { id: this.generateId(), role: 'user', text: question },
    ]);
    this.draft.set('');
    this.errorMessage.set(null);
    this.isLoading.set(true);
    this.scrollToBottom();

    this.odooService.ask(question).subscribe({
      next: (res) => {
        this.messages.update((items) => [
          ...items,
          { id: this.generateId(), role: 'assistant', text: res.answer },
        ]);
        this.isLoading.set(false);
        this.scrollToBottom();
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading.set(false);
        if (err.status === 503) {
          this.errorMessage.set(this.lang.translate('odoo.unreachable'));
        } else {
          const detail = err.error?.detail;
          this.errorMessage.set(
            typeof detail === 'string' ? detail : this.lang.translate('odoo.chatCouldNotAnswer'),
          );
        }
        this.scrollToBottom();
      },
    });
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  private scrollToBottom(): void {
    queueMicrotask(() => {
      const el = this.scrollContainer?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  private generateId(): string {
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}
