// Below this RMS level (~-50 dBFS) a recording has no usable sound: a muted
// mic or the wrong input device reads ~0, while quiet speech is ~0.02+.
const SILENCE_RMS = 0.003;
const SAMPLE_MS = 100;

/**
 * Watches a live microphone stream for sound, so a silent recording (muted
 * mic, wrong input device) can be caught in the browser instead of being
 * uploaded and coming back as "couldn't understand that".
 *
 * Errs towards "heard sound": if the level can't be measured (no Web Audio,
 * or the AudioContext never started), stop() returns true and the recording
 * goes through as before.
 */
export class MicLevelMonitor {
  private ctx: AudioContext | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private measured = false;
  private peak = 0;

  constructor(stream: MediaStream) {
    try {
      const ctx = new AudioContext();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const samples = new Float32Array(analyser.fftSize);
      void ctx.resume().catch(() => undefined);
      this.timer = setInterval(() => {
        if (ctx.state !== 'running') return;
        analyser.getFloatTimeDomainData(samples);
        let sum = 0;
        for (const v of samples) sum += v * v;
        this.peak = Math.max(this.peak, Math.sqrt(sum / samples.length));
        this.measured = true;
      }, SAMPLE_MS);
      this.ctx = ctx;
    } catch {
      // Web Audio unavailable: stop() reports sound, so nothing is blocked.
    }
  }

  /** Stops monitoring. False only when the mic was measured and stayed silent. */
  stop(): boolean {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
    void this.ctx?.close().catch(() => undefined);
    this.ctx = null;
    return !this.measured || this.peak >= SILENCE_RMS;
  }
}
