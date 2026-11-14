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
import { Location } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { OdooChartData, OdooHistoryMessage, OdooSuggestedQuestion } from '../../../core/models/odoo.models';
import { AuthService } from '../../../core/services/auth.service';
import { LanguageService } from '../../../core/services/language.service';
import { OdooService } from '../../../core/services/odoo.service';
import { OdooSuggestedQuestionsService } from '../../../core/services/odoo-suggested-questions.service';
import { SimpleChart, SimpleChartData } from '../../../shared/simple-chart/simple-chart';
import { MicLevelMonitor } from '../../../shared/utils/mic-level';

type VoiceStatus = 'idle' | 'listening' | 'thinking' | 'speaking';

/** Keep in sync with .vita-insights__input's max-height in vita-insights.scss. */
const MAX_TEXTAREA_HEIGHT_PX = 150;

interface VitaInsightsMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  speechObjectUrl?: string;
  chart?: SimpleChartData;
}

function toSimpleChartData(chart: OdooChartData): SimpleChartData {
  return {
    chartType: chart.chart_type,
    title: chart.title,
    labels: chart.labels,
    values: chart.values,
  };
}

@Component({
  selector: 'app-vita-insights',
  imports: [FormsModule, SimpleChart],
  templateUrl: './vita-insights.html',
  styleUrl: './vita-insights.scss',
})
export class VitaInsights implements OnInit, OnDestroy {
  private readonly odooService = inject(OdooService);
  private readonly odooSuggestedQuestionsService = inject(OdooSuggestedQuestionsService);
  private readonly auth = inject(AuthService);
  private readonly location = inject(Location);
  private readonly router = inject(Router);
  readonly lang = inject(LanguageService);

  @ViewChild('scrollContainer') private scrollContainer?: ElementRef<HTMLDivElement>;
  @ViewChild('messageInput') private messageInput?: ElementRef<HTMLTextAreaElement>;

  private readonly rawObjectUrls: string[] = [];
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private pendingSend = false;
  private timerInterval: ReturnType<typeof setInterval> | null = null;
  private currentAudio: HTMLAudioElement | null = null;
  private currentAudioUrl: string | null = null;
  private speakSubscription: Subscription | null = null;

  readonly messages = signal<VitaInsightsMessage[]>([]);
  readonly draft = signal('');
  readonly isLoading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly voiceStatus = signal<VoiceStatus>('idle');
  readonly recordingSeconds = signal(0);

  readonly suggestedQuestions = signal<OdooSuggestedQuestion[]>([]);
  readonly showManagePanel = signal(false);
  readonly manageError = signal<string | null>(null);
  readonly newQuestionText = signal('');
  readonly isAddingQuestion = signal(false);
  readonly isAdmin = computed(() => this.auth.isAdmin());

  /** Return to the previous page; fall back to chat when the page was opened directly. */
  goBack(): void {
    if (window.history.length > 1) {
      this.location.back();
    } else {
      this.router.navigate(['/chat']);
    }
  }

  readonly recordingTime = computed(() => {
    const s = this.recordingSeconds();
    const mm = Math.floor(s / 60).toString().padStart(2, '0');
    const ss = (s % 60).toString().padStart(2, '0');
    return `${mm}:${ss}`;
  });

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
    this.loadSuggestedQuestions();
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

    const history: OdooHistoryMessage[] = this.messages().map((m) => ({
      role: m.role,
      content: m.text,
    }));

    this.messages.update((items) => [
      ...items,
      { id: this.generateId(), role: 'user', text: question },
    ]);
    this.draft.set('');
    this.resetTextareaHeight();
    this.errorMessage.set(null);
    this.isLoading.set(true);
    this.scrollToBottom();

    this.odooService.ask(question, history).subscribe({
      next: (res) => {
        this.messages.update((items) => [
          ...items,
          {
            id: this.generateId(),
            role: 'assistant',
            text: res.answer,
            chart: res.chart ? toSimpleChartData(res.chart) : undefined,
          },
        ]);
        this.isLoading.set(false);
        this.scrollToBottom();
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading.set(false);
        if (err.status === 403) {
          this.errorMessage.set(this.lang.translate('vitaInsights.forbidden'));
        } else if (err.status === 503) {
          this.errorMessage.set(this.lang.translate('vitaInsights.unreachable'));
        } else {
          const detail = err.error?.detail;
          this.errorMessage.set(
            typeof detail === 'string' ? detail : this.lang.translate('vitaInsights.couldNotAnswer'),
          );
        }
        this.scrollToBottom();
      },
    });
  }

  displaySuggestedQuestion(q: OdooSuggestedQuestion): string {
    return this.lang.lang() === 'ar' ? q.question_ar || q.question : q.question;
  }

  selectSuggestedQuestion(q: OdooSuggestedQuestion): void {
    this.draft.set(this.displaySuggestedQuestion(q));
    this.send();
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
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

  // ──────────── Suggested questions management (admin only) ────────────

  toggleManagePanel(): void {
    this.showManagePanel.update((open) => !open);
  }

  addSuggestedQuestion(): void {
    const question = this.newQuestionText().trim();
    if (!question || this.isAddingQuestion()) return;

    this.isAddingQuestion.set(true);
    this.manageError.set(null);

    this.odooSuggestedQuestionsService.add(question).subscribe({
      next: (q) => {
        this.suggestedQuestions.update((items) => [...items, q]);
        this.newQuestionText.set('');
        this.isAddingQuestion.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.isAddingQuestion.set(false);
        const detail = err.error?.detail;
        this.manageError.set(
          typeof detail === 'string' ? detail : this.lang.translate('vitaInsights.suggestedManageError'),
        );
      },
    });
  }

  deleteSuggestedQuestion(q: OdooSuggestedQuestion): void {
    this.manageError.set(null);
    this.odooSuggestedQuestionsService.delete(q.id).subscribe({
      next: () => {
        this.suggestedQuestions.update((items) => items.filter((item) => item.id !== q.id));
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.manageError.set(
          typeof detail === 'string' ? detail : this.lang.translate('vitaInsights.suggestedManageError'),
        );
      },
    });
  }

  private loadSuggestedQuestions(): void {
    this.odooSuggestedQuestionsService.list().subscribe({
      next: (qs) => this.suggestedQuestions.set(qs),
      error: () => {
        // Non-critical for the chat flow itself — just skip showing chips.
      },
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
    this.odooService.transcribe(audioBlob).subscribe({
      next: (res) => {
        const text = res.text?.trim();
        if (text) {
          this.sendVoiceQuestion(text);
        } else {
          this.voiceStatus.set('idle');
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

    const history: OdooHistoryMessage[] = this.messages().map((m) => ({
      role: m.role,
      content: m.text,
    }));

    this.messages.update((items) => [
      ...items,
      { id: this.generateId(), role: 'user', text: question },
    ]);
    this.scrollToBottom();
    this.voiceStatus.set('thinking');
    this.errorMessage.set(null);

    this.odooService.ask(question, history).subscribe({
      next: (res) => {
        const newMessage: VitaInsightsMessage = {
          id: this.generateId(),
          role: 'assistant',
          text: res.answer,
          chart: res.chart ? toSimpleChartData(res.chart) : undefined,
        };
        this.messages.update((items) => [...items, newMessage]);
        this.scrollToBottom();
        this.speakResponse(res.answer, newMessage.id);
      },
      error: (err: HttpErrorResponse) => {
        this.voiceStatus.set('idle');
        if (err.status === 403) {
          this.errorMessage.set(this.lang.translate('vitaInsights.forbidden'));
        } else if (err.status === 503) {
          this.errorMessage.set(this.lang.translate('vitaInsights.unreachable'));
        } else {
          const detail = err.error?.detail;
          this.errorMessage.set(
            typeof detail === 'string' ? detail : this.lang.translate('vitaInsights.couldNotAnswer'),
          );
        }
        this.scrollToBottom();
      },
    });
  }

  private speakResponse(text: string, messageId: string): void {
    this.voiceStatus.set('speaking');
    const langCode = this.detectTtsLanguage(text);

    this.speakSubscription = this.odooService.speak(text, langCode).subscribe({
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

  // ──────────── Shared helpers ────────────

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
