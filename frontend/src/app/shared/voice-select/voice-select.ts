import { Component, ElementRef, HostListener, ViewChild, model, signal } from '@angular/core';

// Gemini prebuilt TTS voice names (lowercase to match services/tts.py's VOICE_NAMES keys).
export type TtsVoice = 'zephyr' | 'puck' | 'kore' | 'charon' | 'leda' | 'fenrir';

export const TTS_VOICES: TtsVoice[] = ['zephyr', 'puck', 'kore', 'charon', 'leda', 'fenrir'];

@Component({
  selector: 'app-voice-select',
  templateUrl: './voice-select.html',
  styleUrl: './voice-select.scss',
})
export class VoiceSelect {
  readonly value = model.required<TtsVoice>();
  readonly voices = TTS_VOICES;

  readonly isOpen = signal(false);

  @ViewChild('root') private root?: ElementRef<HTMLDivElement>;

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.isOpen()) return;
    const el = this.root?.nativeElement;
    if (el && !el.contains(event.target as Node)) {
      this.isOpen.set(false);
    }
  }

  @HostListener('document:keydown.escape')
  onEscapeKey(): void {
    this.isOpen.set(false);
  }

  toggle(): void {
    this.isOpen.update((open) => !open);
  }

  select(voice: TtsVoice): void {
    this.value.set(voice);
    this.isOpen.set(false);
  }
}
