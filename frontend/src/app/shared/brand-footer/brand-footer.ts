import { Component, computed, inject } from '@angular/core';
import { LanguageService } from '../../core/services/language.service';
import { ThemeService } from '../../core/services/theme.service';

/**
 * Site-wide footer carrying the Data Analytics & Operations unit logo.
 * Vita Bot is the product; DAO is the department brand behind it, so the
 * logo sits here as "a product of" rather than replacing the tenant logo
 * in the sidebar/topbar. Navy logo on light, white logo on dark (per the
 * brand pack's README — the navy one must never go on a dark background).
 */
@Component({
  selector: 'app-brand-footer',
  templateUrl: './brand-footer.html',
  styleUrl: './brand-footer.scss',
})
export class BrandFooter {
  readonly lang = inject(LanguageService);
  private readonly theme = inject(ThemeService);

  readonly year = new Date().getFullYear();

  readonly logoSrc = computed(() =>
    this.theme.theme() === 'dark'
      ? 'assets/brand/DAO-Layers_Compact_White.svg'
      : 'assets/brand/DAO-Layers_Compact_Navy.svg',
  );
}
