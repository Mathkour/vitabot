import { Component, OnDestroy, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { LanguageService } from '../../core/services/language.service';
import { OdooAccessService } from '../../core/services/odoo-access.service';
import { SupportTicketsService } from '../../core/services/support-tickets.service';
import { TenantThemeService } from '../../core/services/tenant-theme.service';
import { UnansweredQuestionsService } from '../../core/services/unanswered-questions.service';

const PENDING_TICKETS_POLL_MS = 45000;
const VITA_CARE_TENANT_NAME = 'Vita Care';

type Badge = 'tickets' | 'unanswered';

interface NavItem {
  labelKey: string;
  route: string;
  icon: string;
  badge?: Badge;
  /** Shown only when this returns true; always shown when omitted. */
  visible?: () => boolean;
}

interface NavSection {
  /** Heading; omitted for the top (Dashboard) group. */
  titleKey?: string;
  items: NavItem[];
}

@Component({
  selector: 'app-sidebar',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss',
})
export class Sidebar implements OnInit, OnDestroy {
  readonly lang = inject(LanguageService);
  readonly tenantTheme = inject(TenantThemeService);
  private readonly authService = inject(AuthService);
  private readonly supportTicketsService = inject(SupportTicketsService);
  private readonly odooAccess = inject(OdooAccessService);
  private readonly unansweredQuestionsService = inject(UnansweredQuestionsService);
  readonly openUnansweredCount = this.unansweredQuestionsService.openCountValue;
  private pendingTicketsPollTimer: ReturnType<typeof setInterval> | null = null;

  readonly pendingTicketsCount = signal(0);

  /** Whether the sidebar is open as a mobile off-canvas overlay (ignored above the mobile breakpoint). */
  readonly open = input(false);
  /** Emitted when a nav link (or the brand) is activated, so the host can close the mobile overlay. */
  readonly linkActivated = output<void>();

  private readonly isVitaCare = computed(() => this.tenantTheme.tenantName() === VITA_CARE_TENANT_NAME);

  readonly homeRoute = computed(() => (this.authService.isCompanyAdmin() ? '/users' : '/dashboard'));

  // A company_admin only reaches /users and /support-tickets-admin
  // (companyAdminGuard); every other page denies them, so they get just
  // those two links, ungrouped.
  private readonly companyAdminSections: NavSection[] = [
    {
      items: [
        { labelKey: 'nav.addUsers', route: '/users', icon: 'group_add' },
        { labelKey: 'nav.supportTickets', route: '/support-tickets-admin', icon: 'confirmation_number', badge: 'tickets' },
      ],
    },
  ];

  private readonly adminSections: NavSection[] = [
    { items: [{ labelKey: 'nav.dashboard', route: '/dashboard', icon: 'space_dashboard' }] },
    {
      titleKey: 'nav.section.content',
      items: [
        { labelKey: 'nav.knowledgeBase', route: '/knowledge-base', icon: 'auto_stories' },
        { labelKey: 'nav.faq', route: '/faq-management', icon: 'help_center' },
        { labelKey: 'nav.unansweredQuestions', route: '/unanswered-questions', icon: 'contact_support', badge: 'unanswered' },
        { labelKey: 'nav.answerFeedback', route: '/answer-feedback', icon: 'thumb_down' },
      ],
    },
    {
      titleKey: 'nav.section.people',
      items: [
        { labelKey: 'nav.addUsers', route: '/users', icon: 'group' },
        // Companies are only wired up for Vita Care (require_vita_care_admin).
        { labelKey: 'nav.companies', route: '/companies', icon: 'domain', visible: () => this.isVitaCare() },
        { labelKey: 'nav.conversations', route: '/conversations', icon: 'forum' },
      ],
    },
    {
      titleKey: 'nav.section.support',
      items: [
        { labelKey: 'nav.supportTickets', route: '/support-tickets-admin', icon: 'confirmation_number', badge: 'tickets' },
      ],
    },
    {
      titleKey: 'nav.section.insights',
      items: [
        { labelKey: 'nav.analytics', route: '/analytics', icon: 'monitoring' },
        { labelKey: 'nav.activityLog', route: '/activity-log', icon: 'history' },
      ],
    },
    {
      titleKey: 'nav.section.tools',
      items: [
        { labelKey: 'nav.testBot', route: '/chat', icon: 'chat' },
        { labelKey: 'nav.adminAssistant', route: '/admin-assistant', icon: 'support_agent' },
        // Hidden unless the backend says this user may use it (OdooAccessService).
        { labelKey: 'nav.vitaInsights', route: '/vita-insights', icon: 'database', visible: () => this.isVitaCare() && this.odooAccess.allowed() },
        // Settings temporarily hidden — do not delete. Matching route is also
        // commented out in app.routes.ts.
        // { labelKey: 'nav.settings', route: '/settings', icon: 'settings' },
      ],
    },
  ];

  readonly sections = computed<NavSection[]>(() => {
    const source = this.authService.isCompanyAdmin() ? this.companyAdminSections : this.adminSections;
    return source
      .map((s) => ({ ...s, items: s.items.filter((i) => !i.visible || i.visible()) }))
      .filter((s) => s.items.length > 0);
  });

  badgeCount(badge: Badge | undefined): number {
    if (badge === 'tickets') return this.pendingTicketsCount();
    if (badge === 'unanswered') return this.openUnansweredCount();
    return 0;
  }

  ngOnInit(): void {
    if (this.isVitaCare() && !this.authService.isCompanyAdmin()) {
      this.odooAccess.refresh();
    }
    this.pollPendingTickets();
    this.pendingTicketsPollTimer = setInterval(() => this.pollPendingTickets(), PENDING_TICKETS_POLL_MS);
  }

  ngOnDestroy(): void {
    if (this.pendingTicketsPollTimer) clearInterval(this.pendingTicketsPollTimer);
  }

  private pollPendingTickets(): void {
    this.supportTicketsService.pendingCount().subscribe({
      next: (res) => this.pendingTicketsCount.set(res.count),
      error: () => {},
    });
    // Tenant admins only — the endpoint (and page) deny company_admin.
    if (!this.authService.isCompanyAdmin()) {
      this.unansweredQuestionsService.refreshOpenCount();
    }
  }
}
