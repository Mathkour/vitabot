import { Component, computed, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { Sidebar } from '../sidebar/sidebar';
import { Topbar } from '../topbar/topbar';

/**
 * Shell for routes shared between the admin and member areas (chat, profile,
 * vita-insights — see sharedPageGuard and app.routes.ts).
 * These pages used to pick their shell from the /admin/* vs /chat/* URL
 * prefix; flattening the routes removed that prefix, so the shell is chosen
 * here instead, from the visiting user's actual role. Only one
 * <router-outlet> ever exists in the DOM (the @if swaps decoration around
 * it, not the outlet itself) — two simultaneous outlets at the same route
 * level would confuse the router.
 *
 * AuthService is injected directly (not lazily) because this is a component
 * constructed during route activation, long after bootstrap and after the
 * route's guards have already run and used AuthService themselves — none of
 * the NG0200 risk from the last two fixes (that was specifically about
 * *service* constructors racing an HTTP interceptor during eager app-boot
 * construction) applies here.
 */
@Component({
  selector: 'app-role-layout',
  imports: [RouterOutlet, Sidebar, Topbar],
  templateUrl: './role-layout.html',
  styleUrl: './role-layout.scss',
})
export class RoleLayout {
  private readonly auth = inject(AuthService);

  // Only reachable here at all if logged in (sharedPageGuard/memberGuard
  // already enforce that) and, for a superadmin, only while acting as a
  // tenant (sharedPageGuard redirects a non-acting superadmin to
  // /superadmin before this component is ever created) — so isAdmin() ||
  // isSuperadmin() is exactly "should see the admin sidebar shell".
  readonly isAdminArea = computed(() => this.auth.isAdmin() || this.auth.isSuperadmin());

  /** Mobile off-canvas sidebar state — irrelevant above the sidebar's mobile breakpoint. */
  readonly isMobileSidebarOpen = signal(false);

  toggleMobileSidebar(): void {
    this.isMobileSidebarOpen.update((open) => !open);
  }

  closeMobileSidebar(): void {
    this.isMobileSidebarOpen.set(false);
  }
}
