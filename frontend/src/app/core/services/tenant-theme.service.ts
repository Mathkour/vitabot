import { HttpClient } from '@angular/common/http';
import { Injectable, computed, signal } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { environment } from '../../../environments/environment';
import { skipLoadingIndicator } from '../interceptors/loading-indicator.interceptor';
import { TenantBranding } from '../models/tenant.models';

const ROLE_KEY = 'creditplus_role';
const ACTING_TENANT_KEY = 'creditplus_acting_tenant';
const BRANDING_KEY = 'creditplus_tenant_branding';
const DEFAULT_APP_TITLE = 'My Chatbot';
const DEFAULT_TAB_TITLE = 'My Chatbot Supplier Finance';
const DEFAULT_FAVICON = 'logo.png';
const DEFAULT_PRIMARY = '#16244c';

/** Fixed theme for the superadmin role — never derived from tenant branding. */
const SUPERADMIN_THEME = {
  primary: '#1A1625',
  primaryDark: '#0F0C14',
  accent: '#7C3AED',
  accentLight: 'rgba(124, 58, 237, 0.15)',
  textOnPrimary: '#FFFFFF',
};

const HEX_RE = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i;

function hexToRgb(hex: string): [number, number, number] | null {
  const match = HEX_RE.exec(hex.trim());
  if (!match) {
    return null;
  }
  return [parseInt(match[1], 16), parseInt(match[2], 16), parseInt(match[3], 16)];
}

function toHexChannel(n: number): string {
  return Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
}

function darken(hex: string, amount: number): string {
  const rgb = hexToRgb(hex);
  if (!rgb) {
    return hex;
  }
  const [r, g, b] = rgb;
  return `#${toHexChannel(r * (1 - amount))}${toHexChannel(g * (1 - amount))}${toHexChannel(b * (1 - amount))}`;
}

/** RGB (0-255 each) → HSL as [hue 0-360, saturation 0-100, lightness 0-100]. */
function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;

  if (max === min) {
    return [0, 0, l * 100];
  }

  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h: number;
  switch (max) {
    case rn:
      h = (gn - bn) / d + (gn < bn ? 6 : 0);
      break;
    case gn:
      h = (bn - rn) / d + 2;
      break;
    default:
      h = (rn - gn) / d + 4;
  }
  return [h * 60, s * 100, l * 100];
}

/** HSL (hue 0-360, saturation/lightness 0-100) → hex color. */
function hslToHex(h: number, s: number, l: number): string {
  const hh = ((h % 360) + 360) % 360;
  const ss = Math.max(0, Math.min(100, s)) / 100;
  const ll = Math.max(0, Math.min(100, l)) / 100;
  const c = (1 - Math.abs(2 * ll - 1)) * ss;
  const x = c * (1 - Math.abs(((hh / 60) % 2) - 1));
  const m = ll - c / 2;

  let rp = 0;
  let gp = 0;
  let bp = 0;
  if (hh < 60) {
    [rp, gp, bp] = [c, x, 0];
  } else if (hh < 120) {
    [rp, gp, bp] = [x, c, 0];
  } else if (hh < 180) {
    [rp, gp, bp] = [0, c, x];
  } else if (hh < 240) {
    [rp, gp, bp] = [0, x, c];
  } else if (hh < 300) {
    [rp, gp, bp] = [x, 0, c];
  } else {
    [rp, gp, bp] = [c, 0, x];
  }

  return `#${toHexChannel((rp + m) * 255)}${toHexChannel((gp + m) * 255)}${toHexChannel((bp + m) * 255)}`;
}

/** Reshades `hex` to a target lightness (0-100), keeping its hue and optionally scaling saturation. */
function shade(hex: string, lightness: number, saturationFactor = 1): string {
  const rgb = hexToRgb(hex);
  if (!rgb) {
    return hex;
  }
  const [h, s] = rgbToHsl(...rgb);
  return hslToHex(h, s * saturationFactor, lightness);
}

interface DarkSurfaceShades {
  bg: string;
  surface: string;
  surface2: string;
  border: string;
}

/** Derives the dark-mode surface ramp from a brand primary hex, keeping its hue. */
function darkSurfaceShadesFrom(primaryHex: string): DarkSurfaceShades {
  return {
    bg: shade(primaryHex, 9, 0.7),
    surface: shade(primaryHex, 15, 1),
    surface2: shade(primaryHex, 20, 1),
    border: shade(primaryHex, 28, 1),
  };
}

@Injectable({ providedIn: 'root' })
export class TenantThemeService {
  readonly logoUrl = signal<string | null>(null);
  readonly tenantName = signal<string | null>(null);

  readonly appTitle = computed(() => {
    const name = this.tenantName();
    const firstWord = name?.trim().split(/\s+/)[0];
    return firstWord ? `${firstWord} Bot` : DEFAULT_APP_TITLE;
  });

  readonly tabTitle = computed(() => {
    const name = this.tenantName();
    const firstWord = name?.trim().split(/\s+/)[0];
    return firstWord ? `${firstWord} Bot` : DEFAULT_TAB_TITLE;
  });

  constructor(
    private readonly http: HttpClient,
    private readonly titleService: Title,
  ) {
    // A superadmin acting as a tenant always shows that tenant's branding —
    // even across a refresh — so this check comes before the role check below.
    const actingBranding = this.readActingTenantBranding();
    if (actingBranding) {
      this.applyBranding(actingBranding);
      return;
    }

    if (localStorage.getItem(ROLE_KEY) === 'superadmin') {
      this.applySuperadminTheme();
      return;
    }

    this.applyBranding(this.readCachedBranding());
    if (localStorage.getItem(ROLE_KEY)) {
      this.fetchBranding();
    }
  }

  applyBranding(tenant: TenantBranding | null | undefined): void {
    if (tenant) {
      localStorage.setItem(BRANDING_KEY, JSON.stringify(tenant));
    }

    const root = document.documentElement.style;

    if (tenant?.primary_color) {
      root.setProperty('--primary', tenant.primary_color);
      root.setProperty('--primary-dark', darken(tenant.primary_color, 0.15));
    } else {
      root.removeProperty('--primary');
      root.removeProperty('--primary-dark');
    }

    if (tenant?.action_color) {
      root.setProperty('--accent', tenant.action_color);
    } else {
      root.removeProperty('--accent');
    }
    // --accent-light is intentionally never set here — it's derived in CSS via
    // color-mix() from --accent, so light/dark mode can blend it differently
    // (see styles.scss) instead of a single JS-computed value bleeding into dark mode.

    // Dark-mode surfaces are always hue-derived from the active primary — the
    // tenant's if branded, otherwise the default brand primary — so dark mode
    // never falls back to a hue-less neutral gray regardless of branding.
    const shades = darkSurfaceShadesFrom(tenant?.primary_color || DEFAULT_PRIMARY);
    root.setProperty('--dark-bg', shades.bg);
    root.setProperty('--dark-surface', shades.surface);
    root.setProperty('--dark-surface-2', shades.surface2);
    root.setProperty('--dark-border', shades.border);

    this.logoUrl.set(tenant?.logo_path ?? null);
    this.tenantName.set(tenant?.name ?? null);
    this.titleService.setTitle(this.tabTitle());

    const favicon = document.getElementById('app-favicon') as HTMLLinkElement | null;
    if (favicon) {
      favicon.href = tenant?.logo_path || DEFAULT_FAVICON;
    }
  }

  /**
   * Fixed theme for the "System" superadmin tenant, which has no branding
   * colors of its own. Skips tenant branding entirely — never call this
   * alongside applyBranding() for the same session.
   */
  applySuperadminTheme(): void {
    const root = document.documentElement.style;
    root.setProperty('--primary', SUPERADMIN_THEME.primary);
    root.setProperty('--primary-dark', SUPERADMIN_THEME.primaryDark);
    root.setProperty('--accent', SUPERADMIN_THEME.accent);
    root.setProperty('--accent-light', SUPERADMIN_THEME.accentLight);
    root.setProperty('--text-on-primary', SUPERADMIN_THEME.textOnPrimary);

    const shades = darkSurfaceShadesFrom(SUPERADMIN_THEME.primary);
    root.setProperty('--dark-bg', shades.bg);
    root.setProperty('--dark-surface', shades.surface);
    root.setProperty('--dark-surface-2', shades.surface2);
    root.setProperty('--dark-border', shades.border);

    this.logoUrl.set(null);
    this.tenantName.set(null);
    this.titleService.setTitle(DEFAULT_TAB_TITLE);

    const favicon = document.getElementById('app-favicon') as HTMLLinkElement | null;
    if (favicon) {
      favicon.href = DEFAULT_FAVICON;
    }
  }

  resetTheme(): void {
    localStorage.removeItem(BRANDING_KEY);
    this.applyBranding(null);
  }

  private fetchBranding(): void {
    this.http
      .get<TenantBranding>(`${environment.apiBaseUrl}/tenants/me/branding`, {
        context: skipLoadingIndicator(),
      })
      .subscribe({
        next: (tenant) => this.applyBranding(tenant),
        error: () => {},
      });
  }

  private readActingTenantBranding(): TenantBranding | null {
    const raw = sessionStorage.getItem(ACTING_TENANT_KEY);
    if (!raw) {
      return null;
    }
    try {
      const parsed = JSON.parse(raw) as { branding?: TenantBranding };
      return parsed.branding ?? null;
    } catch {
      return null;
    }
  }

  private readCachedBranding(): TenantBranding | null {
    const raw = localStorage.getItem(BRANDING_KEY);
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw) as TenantBranding;
    } catch {
      return null;
    }
  }
}
