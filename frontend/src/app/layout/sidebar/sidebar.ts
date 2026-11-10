import { Component, OnDestroy, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { LanguageService } from '../../core/services/language.service';
import { OdooAccessService } from '../../core/services/odoo-access.service';
import { SupportTicketsService } from '../../core/services/support-tickets.service';
import { TenantThemeService } from '../../core/services/tenant-theme.service';
import { UnansweredQuestionsService } from '../../core/services/unanswered-questions.service';

const PENDING_TICKETS_POLL_MS = 45000;

interface NavItem {
  labelKey: string;
  route: string;
  icon: string;
}

const VITA_CARE_TENANT_NAME = 'Vita Care';

const FULL_ADMIN_NAV_ITEMS: NavItem[] = [
  { labelKey: 'nav.knowledgeBase', route: '/knowledge-base', icon: 'auto_stories' },
  { labelKey: 'nav.addUsers', route: '/users', icon: 'group_add' },
  { labelKey: 'nav.conversations', route: '/conversations', icon: 'forum' },
  { labelKey: 'nav.chat', route: '/chat', icon: 'chat' },
  { labelKey: 'nav.adminAssistant', route: '/admin-assistant', icon: 'support_agent' },
  { labelKey: 'nav.faq', route: '/faq-management', icon: 'help_center' },
  { labelKey: 'nav.analytics', route: '/analytics', icon: 'insights' },
  { labelKey: 'nav.unansweredQuestions', route: '/unanswered-questions', icon: 'contact_support' },
  { labelKey: 'nav.supportTickets', route: '/support-tickets-admin', icon: 'confirmation_number' },
  // Settings temporarily hidden — do not delete. Matching route is also
  // commented out in app.routes.ts.
  // { labelKey: 'nav.settings', route: '/settings', icon: 'settings' },
];

// Only the pages a company_admin can actually use — they reach AdminLayout
// (and therefore this sidebar) via /users (companyAdminGuard), but every
// other link here is still plain adminGuard and would just deny them.
const COMPANY_ADMIN_NAV_ITEMS: NavItem[] = [
  { labelKey: 'nav.addUsers', route: '/users', icon: 'group_add' },
  { labelKey: 'nav.supportTickets', route: '/support-tickets-admin', icon: 'confirmation_number' },
];

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

  // Neither of these is reachable by a company_admin (shared-page.guard.ts
  // explicitly denies that role) — hidden for them so the sidebar doesn't
  // show a link that always dead-ends at /access-denied. Ask Odoo is also
  // hidden unless the backend says this user may use it (OdooAccessService).
  readonly showVitaInsights = computed(
    () =>
      this.tenantTheme.tenantName() === VITA_CARE_TENANT_NAME &&
      !this.authService.isCompanyAdmin() &&
      this.odooAccess.allowed(),
  );
  // Companies feature is schema-generic but only wired up for Vita Care for
  // now (see require_vita_care_admin on the backend) — same gating pattern
  // as Ask Odoo above. Tenant admin only, never a company_admin.
  readonly showCompanies = computed(
    () => this.tenantTheme.tenantName() === VITA_CARE_TENANT_NAME && !this.authService.isCompanyAdmin(),
  );

  readonly homeRoute = computed(() => (this.authService.isCompanyAdmin() ? '/users' : '/knowledge-base'));

  readonly navItems = computed<NavItem[]>(() => {
    if (this.authService.isCompanyAdmin()) {
      return COMPANY_ADMIN_NAV_ITEMS;
    }
    const items = [...FULL_ADMIN_NAV_ITEMS];
    if (this.showCompanies()) {
      items.splice(2, 0, { labelKey: 'nav.companies', route: '/companies', icon: 'domain' });
    }
    return items;
  });

  ngOnInit(): void {
    if (this.tenantTheme.tenantName() === VITA_CARE_TENANT_NAME && !this.authService.isCompanyAdmin()) {
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
