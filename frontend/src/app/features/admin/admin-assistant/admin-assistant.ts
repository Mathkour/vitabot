import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  ElementRef,
  OnDestroy,
  ViewChild,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize, Subscription } from 'rxjs';
import { AdminAssistantService } from '../../../core/services/admin-assistant.service';
import { ChatService } from '../../../core/services/chat.service';
import { LanguageService } from '../../../core/services/language.service';

interface AdminChatMessage {
  id: string;
  role: 'user' | 'bot';
  text: string;
  speechObjectUrl?: string;
}

type VoiceStatus = 'idle' | 'listening' | 'thinking' | 'speaking';
// Gemini prebuilt TTS voice names (lowercase to match services/tts.py's VOICE_NAMES keys).
type TtsVoice = 'zephyr' | 'puck' | 'kore' | 'charon' | 'leda' | 'fenrir';

const TTS_VOICES: TtsVoice[] = ['zephyr', 'puck', 'kore', 'charon', 'leda', 'fenrir'];

@Component({
  selector: 'app-admin-assistant',
  imports: [FormsModule],
  templateUrl: './admin-assistant.html',
  styleUrl: './admin-assistant.scss',
})
export class AdminAssistant implements OnDestroy {
  private readonly adminAssistantService = inject(AdminAssistantService);
  private readonly chatService = inject(ChatService);
  readonly lang = inject(LanguageService);
  private readonly rawObjectUrls: string[] = [];
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private pendingSend = false;
  private timerInterval: ReturnType<typeof setInterval> | null = null;
  private currentAudio: HTMLAudioElement | null = null;
  private currentAudioUrl: string | null = null;
  private speakSubscription: Subscription | null = null;

  @ViewChild('scrollContainer') private scrollContainer?: ElementRef<HTMLDivElement>;

  readonly messages = signal<AdminChatMessage[]>([]);
  readonly draft = signal('');
  readonly isLoading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly voiceStatus = signal<VoiceStatus>('idle');
  readonly ttsVoice = signal<TtsVoice>('zephyr');
  readonly ttsVoices = TTS_VOICES;
  readonly recordingSeconds = signal(0);

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

  ngOnDestroy(): void {
    this.rawObjectUrls.forEach((url) => URL.revokeObjectURL(url));
    this.clearTimer();
    this.stopAudio();
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
      this.mediaRecorder = null;
    }
  }

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

    this.adminAssistantService
      .ask(question)
      .pipe(finalize(() => this.isLoading.set(false)))
      .subscribe({
        next: (res) => {
          this.messages.update((items) => [
            ...items,
            { id: this.generateId(), role: 'bot', text: res?.answer ?? this.lang.translate('common.noResponse') },
          ]);
          this.scrollToBottom();
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

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  // ──────────── Voice input (mic → transcribe → ask) ────────────

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
      this.errorMessage.set(this.lang.translate('common.micNotSupported'));
      return;
    }

    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
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
        this.voiceStatus.set('idle');
        if (text) {
          this.draft.set(text);
          this.send();
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

  // ──────────── Voice output (speaker button → speak → stop) ────────────

  playAnswer(message: AdminChatMessage): void {
    if (message.speechObjectUrl) {
      if (
        this.currentAudioUrl === message.speechObjectUrl &&
        this.currentAudio &&
        !this.currentAudio.paused
      ) {
        this.stopAudio();
        return;
      }
      this.playAudioUrl(message.speechObjectUrl);
      return;
    }

    this.voiceStatus.set('speaking');
    const langCode = this.detectTtsLanguage(message.text);

    this.speakSubscription = this.chatService.speak(message.text, langCode, this.ttsVoice()).subscribe({
      next: (blob) => {
        this.speakSubscription = null;
        const objectUrl = URL.createObjectURL(blob);
        this.rawObjectUrls.push(objectUrl);
        this.messages.update((items) =>
          items.map((item) =>
            item.id === message.id ? { ...item, speechObjectUrl: objectUrl } : item,
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

  private detectTtsLanguage(text: string): string {
    const latinChars = (text.match(/[a-zA-Z]/g) ?? []).length;
    const nonSpaceChars = (text.match(/\S/g) ?? []).length;
    return nonSpaceChars > 0 && latinChars / nonSpaceChars > 0.5 ? 'en-US' : 'ar-XA';
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
