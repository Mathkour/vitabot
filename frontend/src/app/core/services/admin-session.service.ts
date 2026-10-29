import { Injectable, Injector, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { TenantBranding } from '../models/tenant.models';
import { SuperadminTenant } from '../models/superadmin.models';
import { TenantThemeService } from './tenant-theme.service';

const ACTING_TENANT_KEY = 'creditplus_acting_tenant';

interface StoredActingTenant {
  id: string;
  name: string | null;
  branding: TenantBranding;
}

@Injectable({ providedIn: 'root' })
export class AdminSessionService {
  // Resolved lazily via Injector.get() in enterTenant()/exitTenant() rather
  // than injected eagerly here — TenantThemeService's own constructor can
  // synchronously fire an HTTP request (fetchBranding(), when a role is
  // already in localStorage), which runs through actingTenantInterceptor,
  // which injects THIS service. If this constructor turns around and asks
  // for TenantThemeService back while it's still mid-construction, Angular
  // reports that as a circular dependency (NG0200) and crashes the app at
  // boot. Deferring the lookup to enterTenant()/exitTenant() — both only
  // ever called well after bootstrap, from user actions — means
  // TenantThemeService is always long since finished constructing by then.
  private readonly injector = inject(Injector);
  private readonly router = inject(Router);

  private readonly stored = this.readStored();

  readonly actingTenantId = signal<string | null>(this.stored?.id ?? null);
  readonly actingTenantName = signal<string | null>(this.stored?.name ?? null);
  readonly actingTenantBranding = signal<TenantBranding | null>(this.stored?.branding ?? null);

  readonly isActing = computed(() => this.actingTenantId() !== null);

  enterTenant(tenant: SuperadminTenant): void {
    const branding: TenantBranding = {
      name: tenant.name,
      primary_color: tenant.primary_color,
      action_color: tenant.action_color,
      logo_path: tenant.logo_path,
    };

    this.actingTenantId.set(tenant.id);
    this.actingTenantName.set(tenant.name);
    this.actingTenantBranding.set(branding);
    sessionStorage.setItem(
      ACTING_TENANT_KEY,
      JSON.stringify({ id: tenant.id, name: tenant.name, branding }),
    );

    this.injector.get(TenantThemeService).applyBranding(branding);
    this.router.navigate(['/knowledge-base']);
  }

  exitTenant(): void {
    this.reset();
    this.injector.get(TenantThemeService).applySuperadminTheme();
    this.router.navigate(['/superadmin']);
  }

  /** Clears acting-tenant state without navigating or touching the theme; used on logout. */
  reset(): void {
    this.actingTenantId.set(null);
    this.actingTenantName.set(null);
    this.actingTenantBranding.set(null);
    sessionStorage.removeItem(ACTING_TENANT_KEY);
  }

  private readStored(): StoredActingTenant | null {
    const raw = sessionStorage.getItem(ACTING_TENANT_KEY);
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw) as StoredActingTenant;
    } catch {
      return null;
    }
  }
}
