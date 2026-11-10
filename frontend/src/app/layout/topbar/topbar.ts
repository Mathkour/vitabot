import { Component, OnDestroy, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { LanguageService } from '../../core/services/language.service';
import { OdooAccessService } from '../../core/services/odoo-access.service';
import { UnseenSupportTicket } from '../../core/models/support-ticket.models';
import { SupportTicketsService } from '../../core/services/support-tickets.service';
import { TenantThemeService } from '../../core/services/tenant-theme.service';
import { ThemeService } from '../../core/services/theme.service';

const HOUSING_BANK_TENANT_NAME = 'Housing Bank';
const VITA_CARE_TENANT_NAME = 'Vita Care';
const UNSEEN_TICKETS_POLL_MS = 45000;

@Component({
  selector: 'app-topbar',
  imports: [RouterLink],
  templateUrl: './topbar.html',
  styleUrl: './topbar.scss',
})
export class Topbar implements OnInit, OnDestroy {
  readonly showBrand = input(false);
  /** Shows a hamburger button (mobile widths only) that emits menuToggle when clicked. */
  readonly showMenuToggle = input(false);
  readonly menuToggle = output<void>();

  readonly auth = inject(AuthService);
  readonly theme = inject(ThemeService);
  readonly lang = inject(LanguageService);
  readonly tenantTheme = inject(TenantThemeService);
  private readonly supportTicketsService = inject(SupportTicketsService);
  private readonly odooAccess = inject(OdooAccessService);
  private readonly router = inject(Router);
  private unseenTicketsPollTimer: ReturnType<typeof setInterval> | null = null;

  readonly isProfileMenuOpen = signal(false);

  // Vita Care-only quick link, shown only when the backend says this user
  // may use Ask Odoo (their company's own Odoo, or Vita Care's for staff
  // without a company) — see OdooAccessService. company_admin is denied
  // the page by sharedPageGuard, so hidden for them too.
  readonly showAskOdoo = computed(
    () =>
      this.tenantTheme.tenantName() === VITA_CARE_TENANT_NAME &&
      !this.auth.isCompanyAdmin() &&
      this.odooAccess.allowed(),
  );
  readonly unseenResolvedTicketsCount = signal(0);
  readonly isNotificationsOpen = signal(false);
  readonly unseenTickets = signal<UnseenSupportTicket[]>([]);

  readonly showSupportBell = computed(
    () => !this.auth.isAdmin() && !this.auth.isSuperadmin() && !this.auth.isCompanyAdmin(),
  );

  // Document Index ("الفهرس") — Housing Bank only, same tenant-name-gated
  // quick-link pattern as Ask Odoo above (regular users have no sidebar,
  // so this topbar quick-link is how they reach it under /chat).
  readonly showDocumentIndex = computed(
    () => this.tenantTheme.tenantName() === HOUSING_BANK_TENANT_NAME,
  );

  // End-user video library ("الفيديوهات") — Vita Care only, same
  // topbar-quick-link pattern as Document Index above (regular users have
  // no sidebar, so this is how they reach it under /chat). The /videos
  // route is memberGuard-gated (admin/superadmin/company_admin all denied,
  // same as /faq), so the link is hidden for those roles rather than
  // dead-ending at /access-denied — admins already browse the same YouTube
  // links via the Library > Videos tab on the knowledge-base management page.
  readonly showVideos = computed(
    () =>
      this.tenantTheme.tenantName() === VITA_CARE_TENANT_NAME &&
      !this.auth.isAdmin() &&
      !this.auth.isSuperadmin() &&
      !this.auth.isCompanyAdmin(),
  );

  toggleLanguage(): void {
    this.lang.toggle();
  }

  toggleTheme(): void {
    this.theme.toggle();
  }

  get displayName(): string {
    const user = this.auth.currentUser();
    return user.username || user.email || '';
  }

  get initials(): string {
    const name = this.displayName;
    return name.charAt(0).toUpperCase() || '?';
  }

  toggleProfileMenu(): void {
    this.isProfileMenuOpen.set(!this.isProfileMenuOpen());
  }

  closeProfileMenu(): void {
    this.isProfileMenuOpen.set(false);
  }

  goToProfile(): void {
    this.closeProfileMenu();
    this.router.navigate(['/profile']);
  }

  goToFaq(): void {
    this.closeProfileMenu();
    this.router.navigate([this.auth.isAdmin() ? '/faq-management' : '/faq']);
  }

  logout(): void {
    this.closeProfileMenu();
    this.auth.logout();
    this.router.navigate(['/auth']);
  }

  goToSupportTickets(): void {
    this.closeNotifications();
    this.router.navigate(['/support-tickets']);
  }

  toggleNotifications(): void {
    const next = !this.isNotificationsOpen();
    this.isNotificationsOpen.set(next);
    if (next) {
      this.closeProfileMenu();
      this.pollUnseenTickets();
    }
  }

  closeNotifications(): void {
    this.isNotificationsOpen.set(false);
  }

  openTicketFromNotification(ticket: UnseenSupportTicket): void {
    this.closeNotifications();
    this.router.navigate(['/support-tickets'], { queryParams: { ticketId: ticket.id } });
  }

  ngOnInit(): void {
    if (this.tenantTheme.tenantName() === VITA_CARE_TENANT_NAME && !this.auth.isCompanyAdmin()) {
      this.odooAccess.refresh();
    }
    if (!this.showSupportBell()) return;
    this.pollUnseenTickets();
    this.unseenTicketsPollTimer = setInterval(() => this.pollUnseenTickets(), UNSEEN_TICKETS_POLL_MS);
  }

  ngOnDestroy(): void {
    if (this.unseenTicketsPollTimer) clearInterval(this.unseenTicketsPollTimer);
  }

  private pollUnseenTickets(): void {
    this.supportTicketsService.myUnseenCount().subscribe({
      next: (res) => this.unseenResolvedTicketsCount.set(res.count),
      error: () => {},
    });
    this.supportTicketsService.myUnseenTickets().subscribe({
      next: (tickets) => this.unseenTickets.set(tickets),
      error: () => {},
    });
  }
}
