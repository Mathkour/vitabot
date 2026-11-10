import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { catchError, forkJoin, of } from 'rxjs';
import { CompanyAnalyticsRow } from '../../../core/models/admin-overview.models';
import {
  SatisfactionStats,
  TenantAnalyticsTimeseriesPoint,
  TopQuestionEntry,
  WeakAnswerEntry,
} from '../../../core/models/tenant-analytics.models';
import { AdminOverviewService, downloadCsv } from '../../../core/services/admin-overview.service';
import { LanguageService } from '../../../core/services/language.service';
import { TenantAnalyticsService } from '../../../core/services/tenant-analytics.service';

type RangeOption = 7 | 30 | 90;

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
  selector: 'app-analytics',
  imports: [RouterLink],
  templateUrl: './analytics.html',
  styleUrl: './analytics.scss',
})
export class Analytics implements OnInit {
  private readonly analyticsService = inject(TenantAnalyticsService);
  private readonly overview = inject(AdminOverviewService);
  readonly lang = inject(LanguageService);

  readonly range = signal<RangeOption>(7);
  readonly rangeOptions: RangeOption[] = [7, 30, 90];

  readonly topQuestions = signal<TopQuestionEntry[]>([]);
  readonly weakAnswers = signal<WeakAnswerEntry[]>([]);
  readonly satisfaction = signal<SatisfactionStats | null>(null);
  readonly timeseries = signal<TenantAnalyticsTimeseriesPoint[]>([]);
  readonly companies = signal<CompanyAnalyticsRow[]>([]);

  readonly isLoading = signal(false);
  readonly loadError = signal<string | null>(null);

  // Same hand-rolled inline-SVG chart approach as
  // features/superadmin/ai-monitoring/ai-monitoring.ts, reused as-is rather
  // than pulling in a charting library for one more line chart.
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

  companyName(row: CompanyAnalyticsRow): string {
    return row.name ?? this.lang.translate('users.noCompany');
  }

  exportTopQuestions(): void {
    downloadCsv(`top-questions-${this.range()}d.csv`,
      [this.lang.translate('tenantAnalytics.colQuestion'), this.lang.translate('tenantAnalytics.colCount')],
      this.topQuestions().map((r) => [r.question, r.count]));
  }

  exportWeakAnswers(): void {
    downloadCsv(`weak-answers-${this.range()}d.csv`,
      [this.lang.translate('tenantAnalytics.colQuestion'), this.lang.translate('tenantAnalytics.colCount'), this.lang.translate('tenantAnalytics.colLastSeen')],
      this.weakAnswers().map((r) => [r.question, r.count, r.last_seen]));
  }

  exportCompanies(): void {
    downloadCsv(`companies-${this.range()}d.csv`,
      ['company', 'users', 'active_users', 'questions', 'unanswered', 'thumbs_up', 'thumbs_down'].map((k) => this.lang.translate('tenantAnalytics.col.' + k)),
      this.companies().map((r) => [this.companyName(r), r.users, r.active_users, r.questions, r.unanswered, r.thumbs_up, r.thumbs_down]));
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
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  private load(): void {
    this.isLoading.set(true);
    this.loadError.set(null);

    const days = this.range();

    forkJoin({
      topQuestions: this.analyticsService.getTopQuestions(days),
      weakAnswers: this.analyticsService.getWeakAnswers(days),
      satisfaction: this.analyticsService.getSatisfaction(days),
      timeseries: this.analyticsService.getTimeseries(days, 'day'),
      // The per-company table is extra: if it fails the rest of the page still shows.
      companies: this.overview.companyAnalytics(days).pipe(catchError(() => of([] as CompanyAnalyticsRow[]))),
    }).subscribe({
      next: ({ topQuestions, weakAnswers, satisfaction, timeseries, companies }) => {
        this.companies.set(companies);
        this.topQuestions.set(topQuestions);
        this.weakAnswers.set(weakAnswers);
        this.satisfaction.set(satisfaction);
        this.timeseries.set(timeseries);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.loadError.set(
          typeof detail === 'string' ? detail : this.lang.translate('tenantAnalytics.couldNotLoad'),
        );
        this.isLoading.set(false);
      },
    });
  }
}
