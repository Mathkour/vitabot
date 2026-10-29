import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { forkJoin } from 'rxjs';
import {
  AiMonitoringErrorEntry,
  AiMonitoringSummary,
  AiMonitoringTimeseriesPoint,
} from '../../../core/models/ai-monitoring.models';
import { AiMonitoringService } from '../../../core/services/ai-monitoring.service';
import { LanguageService } from '../../../core/services/language.service';
import { SuperadminNav } from '../superadmin-nav/superadmin-nav';

type RangeOption = 'today' | 7 | 30 | 90;

interface LinePoint {
  x: number;
  y: number;
}

interface ChartGeometry {
  width: number;
  height: number;
  baselineY: number;
  callsPath: string;
  timePath: string;
  callsPoints: LinePoint[];
  timePoints: LinePoint[];
  labels: { x: number; text: string }[];
}

@Component({
  selector: 'app-ai-monitoring',
  imports: [SuperadminNav],
  templateUrl: './ai-monitoring.html',
  styleUrl: './ai-monitoring.scss',
})
export class AiMonitoring implements OnInit {
  private readonly aiMonitoringService = inject(AiMonitoringService);
  readonly lang = inject(LanguageService);

  readonly range = signal<RangeOption>(7);
  readonly rangeOptions: RangeOption[] = ['today', 7, 30, 90];

  readonly summary = signal<AiMonitoringSummary | null>(null);
  readonly timeseries = signal<AiMonitoringTimeseriesPoint[]>([]);
  readonly errors = signal<AiMonitoringErrorEntry[]>([]);

  readonly isLoading = signal(false);
  readonly loadError = signal<string | null>(null);

  /** True while the currently loaded timeseries is hourly (the "Today" range) — read by
   * formatBucketLabel to switch the chart's X-axis from dates to hour-of-day. */
  private isHourly = false;

  readonly chart = computed<ChartGeometry | null>(() => {
    const points = this.timeseries();
    if (points.length === 0) return null;

    const width = 640;
    const height = 220;
    const paddingTop = 20;
    const paddingBottom = 28;
    const paddingX = 16;
    const plotWidth = width - paddingX * 2;
    const plotHeight = height - paddingTop - paddingBottom;
    const n = points.length;

    const maxCalls = Math.max(...points.map((p) => p.call_count), 1);
    const maxTime = Math.max(...points.map((p) => p.avg_response_time_ms), 1);
    const xStep = n > 1 ? plotWidth / (n - 1) : 0;
    const xFor = (i: number) => paddingX + i * xStep;
    const yForRatio = (ratio: number) => paddingTop + plotHeight - ratio * plotHeight;

    const callsPoints = points.map((p, i) => ({ x: xFor(i), y: yForRatio(p.call_count / maxCalls) }));
    const timePoints = points.map((p, i) => ({
      x: xFor(i),
      y: yForRatio(p.avg_response_time_ms / maxTime),
    }));

    const toPath = (pts: LinePoint[]) =>
      pts.map((pt, i) => `${i === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ');

    // Thin out labels so they don't overlap on a 90-day / hourly view.
    const labelStride = Math.max(1, Math.ceil(n / 8));
    const labels = points
      .map((p, i) => ({ x: xFor(i), text: this.formatBucketLabel(p.bucket) }))
      .filter((_, i) => i % labelStride === 0 || i === n - 1);

    return {
      width,
      height,
      baselineY: paddingTop + plotHeight,
      callsPath: toPath(callsPoints),
      timePath: toPath(timePoints),
      callsPoints,
      timePoints,
      labels,
    };
  });

  ngOnInit(): void {
    this.load();
  }

  selectRange(range: RangeOption): void {
    if (range === this.range()) return;
    this.range.set(range);
    this.load();
  }

  formatDate(value: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  private formatBucketLabel(value: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    if (this.isHourly) {
      return date.toLocaleTimeString(undefined, {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
    }
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  private load(): void {
    this.isLoading.set(true);
    this.loadError.set(null);

    const range = this.range();
    const isToday = range === 'today';
    const summaryDays = isToday ? 1 : range;
    const timeseriesInterval = isToday ? 'hour' : 'day';
    this.isHourly = isToday;

    forkJoin({
      summary: this.aiMonitoringService.getSummary(summaryDays),
      timeseries: this.aiMonitoringService.getTimeseries(summaryDays, timeseriesInterval),
      errors: this.aiMonitoringService.getErrors(50),
    }).subscribe({
      next: ({ summary, timeseries, errors }) => {
        this.summary.set(summary);
        this.timeseries.set(timeseries);
        this.errors.set(errors);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.loadError.set(
          typeof detail === 'string' ? detail : this.lang.translate('aiMonitoring.couldNotLoad'),
        );
        this.isLoading.set(false);
      },
    });
  }
}
