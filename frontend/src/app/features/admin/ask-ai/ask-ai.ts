import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, ViewChild, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AskIndexSource } from '../../../core/models/document-index.models';
import { ChatService } from '../../../core/services/chat.service';
import { DocumentIndexService } from '../../../core/services/document-index.service';
import { LanguageService } from '../../../core/services/language.service';

type VoiceStatus = 'idle' | 'listening' | 'transcribing';

interface AskAiMessage {
  id: number;
  role: 'user' | 'bot';
  text: string;
  sources?: AskIndexSource[];
}

/** Keep in sync with .ask-ai__textarea's max-height in ask-ai.scss. */
const MAX_TEXTAREA_HEIGHT_PX = 120;

@Component({
  selector: 'app-ask-ai',
  imports: [FormsModule],
  templateUrl: './ask-ai.html',
  styleUrl: './ask-ai.scss',
})
export class AskAi {
  private readonly documentIndexService = inject(DocumentIndexService);
  private readonly chatService = inject(ChatService);
  readonly lang = inject(LanguageService);

  @ViewChild('scrollContainer') private scrollContainer?: ElementRef<HTMLDivElement>;
  @ViewChild('questionInput') private questionInput?: ElementRef<HTMLTextAreaElement>;

  readonly question = signal('');
  readonly messages = signal<AskAiMessage[]>([]);
  readonly isAsking = signal(false);
  readonly askError = signal<string | null>(null);
  readonly showEmptyState = computed(() => this.messages().length === 0);

  private nextId = 1;

  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private pendingSend = false;
  private timerInterval: ReturnType<typeof setInterval> | null = null;

  readonly voiceStatus = signal<VoiceStatus>('idle');
  readonly recordingSeconds = signal(0);
  readonly recordingTime = computed(() => {
    const s = this.recordingSeconds();
    const mm = Math.floor(s / 60).toString().padStart(2, '0');
    const ss = (s % 60).toString().padStart(2, '0');
    return `${mm}:${ss}`;
  });

  ask(): void {
    const q = this.question().trim();
    if (!q || this.isAsking()) return;

    this.messages.update((items) => [...items, { id: this.nextId++, role: 'user', text: q }]);
    this.question.set('');
    this.resetTextareaHeight();
    this.scrollToBottom();

    this.isAsking.set(true);
    this.askError.set(null);

    this.documentIndexService.ask(q).subscribe({
      next: (res) => {
        this.messages.update((items) => [
          ...items,
          { id: this.nextId++, role: 'bot', text: res.answer, sources: res.sources },
        ]);
        this.isAsking.set(false);
        this.scrollToBottom();
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.askError.set(typeof detail === 'string' ? detail : this.lang.translate('askAi.error'));
        this.isAsking.set(false);
      },
    });
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.ask();
    }
  }

  autoResizeTextarea(target: EventTarget | null): void {
    const el = target as HTMLTextAreaElement | null;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT_PX)}px`;
  }

  private resetTextareaHeight(): void {
    const el = this.questionInput?.nativeElement;
    if (el) el.style.height = 'auto';
  }

  private scrollToBottom(): void {
    // admin-layout__content (role-layout.scss) is a normal scrolling page,
    // not an internally-scrolled panel, so the page itself is scrolled —
    // not scrollContainer, which has no overflow of its own here.
    queueMicrotask(() => {
      this.scrollContainer?.nativeElement.scrollIntoView({ block: 'end' });
    });
  }

  pageLabel(source: AskIndexSource): string {
    const key = source.file_type === 'pptx' ? 'documentIndex.slide' : 'documentIndex.page';
    return `${this.lang.translate(key)} ${source.page_number}`;
  }

  // ──────────── Voice input ────────────

  toggleVoice(): void {
    if (this.voiceStatus() !== 'idle') return;
    this.startListening();
  }

  cancelRecording(): void {
    this.stopRecording(false);
  }

  sendRecording(): void {
    this.stopRecording(true);
  }

  private startListening(): void {
    if (!navigator.mediaDevices?.getUserMedia) {
      this.askError.set(this.lang.translate('common.micNotSupported'));
      return;
    }

    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      this.askError.set(null);
      this.audioChunks = [];
      const recorder = new MediaRecorder(stream);
      this.mediaRecorder = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) this.audioChunks.push(e.data);
      };

      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const mimeType = recorder.mimeType || 'audio/webm';
        this.mediaRecorder = null;
        const audioBlob = new Blob(this.audioChunks, { type: mimeType });
        this.audioChunks = [];

        if (!this.pendingSend) {
          this.voiceStatus.set('idle');
          return;
        }
        this.pendingSend = false;

        if (audioBlob.size === 0) {
          this.voiceStatus.set('idle');
          return;
        }
        this.transcribeAudio(audioBlob);
      };

      recorder.start();
      this.recordingSeconds.set(0);
      this.timerInterval = setInterval(() => this.recordingSeconds.update((s) => s + 1), 1000);
      this.voiceStatus.set('listening');
    }).catch(() => {
      this.askError.set(this.lang.translate('common.micDenied'));
      this.voiceStatus.set('idle');
    });
  }

  private stopRecording(send: boolean): void {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.clearTimer();
      this.pendingSend = send;
      this.voiceStatus.set(send ? 'transcribing' : 'idle');
      this.mediaRecorder.stop();
    }
  }

  private clearTimer(): void {
    if (this.timerInterval !== null) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }
    this.recordingSeconds.set(0);
  }

  private transcribeAudio(audioBlob: Blob): void {
    this.chatService.transcribe(audioBlob).subscribe({
      next: (res) => {
        const text = res.text?.trim();
        this.voiceStatus.set('idle');
        if (text) {
          this.question.set(text);
          this.ask();
        } else {
          this.askError.set(this.lang.translate('common.voiceNotUnderstood'));
        }
      },
      error: (err: HttpErrorResponse) => {
        this.voiceStatus.set('idle');
        const detail = err.error?.detail;
        this.askError.set(
          typeof detail === 'string' ? detail : this.lang.translate('common.transcriptionFailed'),
        );
      },
    });
  }
}
