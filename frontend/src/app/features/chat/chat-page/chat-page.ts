import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  ElementRef,
  OnDestroy,
  OnInit,
  ViewChild,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { finalize, Subscription } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { Category, SuggestedQuestion } from '../../../core/models/category.models';
import { AskMediaItem, AskResponse, ChatMessage, RatingScore } from '../../../core/models/chat.models';
import { ConversationSummary } from '../../../core/models/conversation.models';
import { CategoriesService } from '../../../core/services/categories.service';
import { ChatService } from '../../../core/services/chat.service';
import { ConversationsService } from '../../../core/services/conversations.service';
import { LanguageService } from '../../../core/services/language.service';
import { SuggestedQuestionsService } from '../../../core/services/suggested-questions.service';
import { SupportTicketsService } from '../../../core/services/support-tickets.service';
import { DisplayNamePipe } from '../../../shared/pipes/display-name.pipe';
import { extractYoutubeId } from '../../../shared/utils/youtube';
import { TtsVoice } from '../../../shared/voice-select/voice-select';
import { MicLevelMonitor } from '../../../shared/utils/mic-level';

type VoiceStatus = 'idle' | 'listening' | 'thinking' | 'speaking';

/** Keep in sync with .chat__input's max-height in chat-page.scss. */
const MAX_TEXTAREA_HEIGHT_PX = 150;

@Component({
  selector: 'app-chat-page',
  imports: [FormsModule, DatePipe, DisplayNamePipe],
  templateUrl: './chat-page.html',
  styleUrl: './chat-page.scss',
})
export class ChatPage implements OnInit, OnDestroy {
  private readonly chatService = inject(ChatService);
  private readonly categoriesService = inject(CategoriesService);
  private readonly suggestedQuestionsService = inject(SuggestedQuestionsService);
  private readonly conversationsService = inject(ConversationsService);
  private readonly supportTicketsService = inject(SupportTicketsService);
  private readonly sanitizer = inject(DomSanitizer);
  readonly lang = inject(LanguageService);
  private conversationId: string | null = null;
  private readonly rawObjectUrls: string[] = [];
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private pendingSend = false;
  private timerInterval: ReturnType<typeof setInterval> | null = null;
  private currentAudio: HTMLAudioElement | null = null;
  private currentAudioUrl: string | null = null;
  private speakSubscription: Subscription | null = null;

  @ViewChild('scrollContainer') private scrollContainer?: ElementRef<HTMLDivElement>;
  @ViewChild('messageInput') private messageInput?: ElementRef<HTMLTextAreaElement>;

  readonly messages = signal<ChatMessage[]>([]);
  readonly draft = signal('');
  readonly isLoading = signal(false);
  readonly errorMessage = signal<string | null>(null);

  readonly supportTicketQuestion = signal('');
  readonly isSupportTicketOpen = signal(false);
  readonly isSubmittingSupportTicket = signal(false);
  readonly supportTicketSubmitted = signal(false);
  readonly supportTicketError = signal<string | null>(null);
  readonly voiceStatus = signal<VoiceStatus>('idle');
  // Fixed — the voice picker UI was removed per request so the user never
  // sees or chooses which voice is speaking.
  readonly ttsVoice: TtsVoice = 'zephyr';
  readonly recordingSeconds = signal(0);

  readonly recordingTime = computed(() => {
    const s = this.recordingSeconds();
    const mm = Math.floor(s / 60).toString().padStart(2, '0');
    const ss = (s % 60).toString().padStart(2, '0');
    return `${mm}:${ss}`;
  });

  readonly categories = signal<Category[]>([]);
  readonly selectedCategoryId = signal<string>('');
  readonly selectedCategory = computed(
    () => this.categories().find((c) => c.id === this.selectedCategoryId()) ?? null,
  );

  readonly suggestedQuestions = signal<SuggestedQuestion[]>([]);
  readonly suggestedQuestionsLoading = signal(false);
  readonly suggestedQuestionsError = signal<string | null>(null);

  readonly showEmptyState = computed(() => this.messages().length === 0);

  readonly voiceStatusLabel = computed(() => {
    switch (this.voiceStatus()) {
      case 'listening': return this.lang.translate('common.listening');
      case 'thinking': return this.lang.translate('common.thinking');
      case 'speaking': return this.lang.translate('common.speaking');
      default: return '';
    }
  });

  readonly voiceStatusIcon = computed(() => {
    switch (this.voiceStatus()) {
      case 'listening': return 'mic';
      case 'thinking': return 'hourglass_top';
      case 'speaking': return 'volume_up';
      default: return '';
    }
  });

  ngOnInit(): void {
    this.categoriesService.listPublished().subscribe({
      next: (cats) => this.categories.set(cats),
    });
  }

  ngOnDestroy(): void {
    this.rawObjectUrls.forEach((url) => URL.revokeObjectURL(url));
    this.clearTimer();
    this.stopAudio();
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
      this.mediaRecorder = null;
    }
  }

  // ──────────── Manual text send ────────────

  send(): void {
    const question = this.draft().trim();
    if (!question || this.isLoading()) return;

    this.messages.update((items) => [
      ...items,
      { id: this.generateId(), role: 'user', text: question },
    ]);
    this.draft.set('');
    this.resetTextareaHeight();
    this.errorMessage.set(null);
    this.isLoading.set(true);
    this.scrollToBottom();

    this.chatService
      .ask({
        question,
        conversation_id: this.conversationId,
        category_id: this.selectedCategoryId() || null,
      })
      .pipe(finalize(() => this.isLoading.set(false)))
      .subscribe({
        next: (res) => {
          if (!res) {
            this.errorMessage.set(this.lang.translate('common.noResponse'));
            this.scrollToBottom();
            return;
          }
          this.processBotResponse(res, false);
        },
        error: (err: HttpErrorResponse) => {
          const detail = err.error?.detail;
          this.errorMessage.set(
            typeof detail === 'string' ? detail : this.lang.translate('common.somethingWrong'),
          );
          this.scrollToBottom();
        },
      });
  }

  // ──────────── Category scope + suggested questions ────────────

  selectCategory(cat: Category | null): void {
    if (this.selectedCategoryId() === (cat?.id ?? '')) return;

    this.selectedCategoryId.set(cat?.id ?? '');
    this.suggestedQuestions.set([]);
    this.suggestedQuestionsError.set(null);

    if (!cat) {
      this.suggestedQuestionsLoading.set(false);
      return;
    }

    this.suggestedQuestionsLoading.set(true);
    this.suggestedQuestionsService.list(cat.id).subscribe({
      next: (qs) => {
        this.suggestedQuestions.set(qs);
        this.suggestedQuestionsLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.suggestedQuestionsError.set(
          typeof detail === 'string' ? detail : this.lang.translate('chat.couldNotLoadQuestions'),
        );
        this.suggestedQuestionsLoading.set(false);
      },
    });
  }

  displayQuestion(q: SuggestedQuestion): string {
    return this.lang.lang() === 'ar' ? q.question_ar || q.question : q.question;
  }

  displayAnswer(q: SuggestedQuestion): string {
    return this.lang.lang() === 'ar' ? q.answer_ar || q.answer : q.answer;
  }

  selectSuggestedQuestion(q: SuggestedQuestion): void {
    const question = this.displayQuestion(q);
    const answer = this.displayAnswer(q);

    if (answer.trim()) {
      this.messages.update((items) => [
        ...items,
        { id: this.generateId(), role: 'user', text: question },
        { id: this.generateId(), role: 'bot', text: answer },
      ]);
      this.scrollToBottom();
      return;
    }

    this.draft.set(question);
    this.send();
  }

  // ──────────── Conversation history ────────────

  readonly isHistoryOpen = signal(false);
  readonly historyLoading = signal(false);
  readonly historyError = signal<string | null>(null);
  readonly historyConversations = signal<ConversationSummary[]>([]);
  readonly expandedHistoryIds = signal<Set<string>>(new Set());

  openHistory(): void {
    this.isHistoryOpen.set(true);
    this.historyError.set(null);
    this.historyLoading.set(true);

    this.conversationsService.getMyConversations().subscribe({
      next: (res) => {
        this.historyConversations.set(res.conversations);
        this.historyLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.historyError.set(
          typeof detail === 'string' ? detail : this.lang.translate('chat.couldNotLoadHistory'),
        );
        this.historyLoading.set(false);
      },
    });
  }

  closeHistory(): void {
    this.isHistoryOpen.set(false);
  }

  toggleHistoryConversation(conversationId: string): void {
    this.expandedHistoryIds.update((s) => {
      const n = new Set(s);
      if (n.has(conversationId)) {
        n.delete(conversationId);
      } else {
        n.add(conversationId);
      }
      return n;
    });
  }

  // ──────────── Voice flow ────────────

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

  replayAudio(speechObjectUrl: string): void {
    if (this.currentAudioUrl === speechObjectUrl && this.currentAudio && !this.currentAudio.paused) {
      this.stopAudio();
      return;
    }
    this.playAudioUrl(speechObjectUrl);
  }

  stopAudio(): void {
    // Cancels an in-flight /speak request too — without this, clicking Stop
    // before the audio actually starts playing (still waiting on synthesis)
    // had no effect: the response would still arrive and start playback.
    this.speakSubscription?.unsubscribe();
    this.speakSubscription = null;
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.currentTime = 0;
      this.currentAudio = null;
    }
    this.currentAudioUrl = null;
    this.voiceStatus.set('idle');
  }

  private playAudioUrl(url: string): void {
    this.stopAudio();
    const audio = new Audio(url);
    this.currentAudio = audio;
    this.currentAudioUrl = url;
    this.voiceStatus.set('speaking');
    audio.onended = () => { this.currentAudio = null; this.currentAudioUrl = null; this.voiceStatus.set('idle'); };
    audio.onerror = () => { this.currentAudio = null; this.currentAudioUrl = null; this.voiceStatus.set('idle'); };
    audio.play().catch(() => { this.currentAudio = null; this.currentAudioUrl = null; this.voiceStatus.set('idle'); });
  }

  private startListening(): void {
    if (!navigator.mediaDevices?.getUserMedia) {
      this.errorMessage.set(this.lang.translate('common.micNotSupported'));
      return;
    }

    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      this.errorMessage.set(null);
      this.audioChunks = [];
      const recorder = new MediaRecorder(stream);
      const micLevel = new MicLevelMonitor(stream);
      this.mediaRecorder = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) this.audioChunks.push(e.data);
      };

      recorder.onstop = () => {
        // Release the microphone immediately.
        stream.getTracks().forEach((t) => t.stop());
        const heardSound = micLevel.stop();
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
        if (!heardSound) {
          // Muted mic / wrong input device: say so, rather than uploading
          // silence and showing the misleading "couldn't understand that".
          this.voiceStatus.set('idle');
          this.errorMessage.set(this.lang.translate('common.micNoSound'));
          return;
        }
        this.transcribeAudio(audioBlob);
      };

      recorder.start();
      this.recordingSeconds.set(0);
      this.timerInterval = setInterval(() => this.recordingSeconds.update((s) => s + 1), 1000);
      this.voiceStatus.set('listening');
    }).catch(() => {
      this.errorMessage.set(this.lang.translate('common.micDenied'));
      this.voiceStatus.set('idle');
    });
  }

  private stopRecording(send: boolean): void {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.clearTimer();
      this.pendingSend = send;
      this.voiceStatus.set(send ? 'thinking' : 'idle');
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
        if (text) {
          this.sendVoiceQuestion(text);
        } else {
          // The transcription service intentionally returns "" when it
          // detects speech it can't confidently transcribe (e.g. an
          // unrecognized language), rather than a wrong/garbled result.
          this.voiceStatus.set('idle');
          this.errorMessage.set(this.lang.translate('common.voiceNotUnderstood'));
        }
      },
      error: (err: HttpErrorResponse) => {
        this.voiceStatus.set('idle');
        const detail = err.error?.detail;
        this.errorMessage.set(
          typeof detail === 'string' ? detail : this.lang.translate('common.transcriptionFailed'),
        );
      },
    });
  }

  private sendVoiceQuestion(question: string): void {
    if (!question) {
      this.voiceStatus.set('idle');
      return;
    }

    this.messages.update((items) => [
      ...items,
      { id: this.generateId(), role: 'user', text: question },
    ]);
    this.scrollToBottom();
    this.voiceStatus.set('thinking');
    this.errorMessage.set(null);

    this.chatService.ask({
      question,
      conversation_id: this.conversationId,
      category_id: this.selectedCategoryId() || null,
    }).subscribe({
      next: (res) => {
        if (!res) {
          this.voiceStatus.set('idle');
          this.errorMessage.set(this.lang.translate('common.noResponse'));
          return;
        }
        this.processBotResponse(res, true);
      },
      error: (err: HttpErrorResponse) => {
        this.voiceStatus.set('idle');
        const detail = err.error?.detail;
        this.errorMessage.set(
          typeof detail === 'string' ? detail : this.lang.translate('common.somethingWrong'),
        );
        this.scrollToBottom();
      },
    });
  }

  // ──────────── Shared bot-response handler ────────────

  private processBotResponse(res: AskResponse, isVoice: boolean): void {
    this.conversationId = res.conversation_id;
    const newMessage: ChatMessage = {
      id: this.generateId(),
      role: 'bot',
      text: res.answer,
      sources: res.sources ?? [],
      messageId: res.message_id,
      rating: null,
      media: res.media ?? null,
      youtubeEmbedUrl: this.buildYoutubeEmbedUrl(res.media),
      slideSource: res.slide_source ?? null,
      offerSupport: res.offer_support ?? false,
    };

    this.messages.update((items) => [...items, newMessage]);
    this.scrollToBottom();

    if (res.media && res.media.type !== 'link') {
      const fullUrl = environment.apiBaseUrl + res.media.url;
      const msgId = newMessage.id;
      this.chatService.fetchMedia(fullUrl).subscribe({
        next: (blob) => {
          const objectUrl = URL.createObjectURL(blob);
          this.rawObjectUrls.push(objectUrl);
          const safeUrl = this.sanitizer.bypassSecurityTrustUrl(objectUrl);
          this.messages.update((items) =>
            items.map((item) =>
              item.id === msgId
                ? { ...item, mediaSafeUrl: safeUrl }
                : item,
            ),
          );
          this.scrollToBottom();
        },
        error: () => {
          this.errorMessage.set(this.lang.translate('chat.couldNotLoadMedia'));
        },
      });
    }

    if (isVoice) {
      this.speakResponse(res.answer, newMessage.id);
    }
  }

  private speakResponse(text: string, messageId: string): void {
    this.voiceStatus.set('speaking');
    const langCode = this.detectTtsLanguage(text);

    this.speakSubscription = this.chatService.speak(text, langCode, this.ttsVoice).subscribe({
      next: (blob) => {
        this.speakSubscription = null;
        const objectUrl = URL.createObjectURL(blob);
        this.rawObjectUrls.push(objectUrl);
        this.messages.update((items) =>
          items.map((item) =>
            item.id === messageId ? { ...item, speechObjectUrl: objectUrl } : item,
          ),
        );
        this.playAudioUrl(objectUrl);
      },
      error: () => {
        this.speakSubscription = null;
        this.voiceStatus.set('idle');
      },
    });
  }

  private detectTtsLanguage(text: string): string {
    const latinChars = (text.match(/[a-zA-Z]/g) ?? []).length;
    const nonSpaceChars = (text.match(/\S/g) ?? []).length;
    return nonSpaceChars > 0 && latinChars / nonSpaceChars > 0.5 ? 'en-US' : 'ar-XA';
  }

  // ──────────── Rating & media helpers ────────────

  private buildYoutubeEmbedUrl(media: AskMediaItem | null | undefined): SafeResourceUrl | null {
    if (!media || media.type !== 'link') {
      return null;
    }
    const videoId = extractYoutubeId(media.url);
    if (!videoId) {
      return null;
    }
    return this.sanitizer.bypassSecurityTrustResourceUrl(
      `https://www.youtube-nocookie.com/embed/${videoId}`,
    );
  }

  rate(message: ChatMessage, score: RatingScore): void {
    if (!message.messageId) return;

    // The backend overwrites the stored rating for this message, so switching
    // 👍 -> 👎 (or back) is allowed at any time — no longer a one-shot action.
    this.chatService.rate({ message_id: message.messageId, score, feedback: null }).subscribe({
      next: () => {
        this.messages.update((items) =>
          items.map((item) => (item.id === message.id ? { ...item, rating: score } : item)),
        );
      },
    });
  }

  openSupportTicket(message: ChatMessage): void {
    const items = this.messages();
    const index = items.findIndex((item) => item.id === message.id);
    let question = '';
    for (let i = index - 1; i >= 0; i--) {
      if (items[i].role === 'user') {
        question = items[i].text;
        break;
      }
    }
    this.supportTicketQuestion.set(question);
    this.supportTicketError.set(null);
    this.supportTicketSubmitted.set(false);
    this.isSupportTicketOpen.set(true);
  }

  closeSupportTicket(): void {
    if (this.isSubmittingSupportTicket()) return;
    this.isSupportTicketOpen.set(false);
  }

  submitSupportTicket(): void {
    const question = this.supportTicketQuestion().trim();
    if (!question || this.isSubmittingSupportTicket()) return;

    this.isSubmittingSupportTicket.set(true);
    this.supportTicketError.set(null);

    this.supportTicketsService.create(question, this.conversationId).subscribe({
      next: () => {
        this.isSubmittingSupportTicket.set(false);
        this.supportTicketSubmitted.set(true);
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmittingSupportTicket.set(false);
        const detail = err.error?.detail;
        this.supportTicketError.set(
          typeof detail === 'string' ? detail : this.lang.translate('supportTicket.couldNotSubmit'),
        );
      },
    });
  }

  /** Grows/shrinks the textarea to fit its content, capped at MAX_TEXTAREA_HEIGHT_PX. */
  autoResizeTextarea(target: EventTarget | null): void {
    const el = target as HTMLTextAreaElement | null;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT_PX)}px`;
  }

  private resetTextareaHeight(): void {
    const el = this.messageInput?.nativeElement;
    if (el) el.style.height = 'auto';
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
