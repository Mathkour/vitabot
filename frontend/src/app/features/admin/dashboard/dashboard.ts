import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DashboardSummary } from '../../../core/models/admin-overview.models';
import { AdminOverviewService } from '../../../core/services/admin-overview.service';
import { AuthService } from '../../../core/services/auth.service';
import { LanguageService } from '../../../core/services/language.service';

/** Admin home: what needs attention now, and how the bot did this period. */
@Component({
  selector: 'app-dashboard',
  imports: [RouterLink, DatePipe, DecimalPipe],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class Dashboard implements OnInit {
  private readonly service = inject(AdminOverviewService);
  private readonly auth = inject(AuthService);
  readonly lang = inject(LanguageService);

  readonly ranges = [7, 30, 90];
  readonly days = signal(7);
  readonly data = signal<DashboardSummary | null>(null);
  readonly isLoading = signal(true);
  readonly loadError = signal<string | null>(null);

  readonly name = computed(() => this.auth.currentUser().username || '');

  /** % change in questions vs the previous period of the same length. */
  readonly questionsTrend = computed(() => {
    const d = this.data();
    if (!d || !d.questions_prev) return null;
    return Math.round(((d.questions - d.questions_prev) / d.questions_prev) * 100);
  });

  readonly chartMax = computed(() => Math.max(1, ...(this.data()?.daily ?? []).map((p) => p.count)));
  readonly attentionTotal = computed(() => {
    const d = this.data();
    return d ? d.open_unanswered + d.feedback_to_review + d.pending_tickets : 0;
  });

  ngOnInit(): void {
    this.load();
  }

  setDays(days: number): void {
    if (days === this.days()) return;
    this.days.set(days);
    this.load();
  }

  barHeight(count: number): number {
    return Math.round((count / this.chartMax()) * 100);
  }

  private load(): void {
    this.isLoading.set(true);
    this.loadError.set(null);
    this.service.dashboard(this.days()).subscribe({
      next: (d) => {
        this.data.set(d);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading.set(false);
        const detail = err.error?.detail;
        this.loadError.set(typeof detail === 'string' ? detail : this.lang.translate('dashboard.couldNotLoad'));
      },
    });
  }
}
