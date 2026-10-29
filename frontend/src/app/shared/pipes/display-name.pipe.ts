import { Pipe, PipeTransform } from '@angular/core';

export interface Nameable {
  display_name?: string | null;
  display_name_ar?: string | null;
  filename: string;
  media_type?: string;
  description?: string;
  description_ar?: string | null;
}

/**
 * Returns the custom display name if set. Links are stored with a
 * placeholder filename ("external_link") since they have no real uploaded
 * file, so that's never shown — links fall back to their description, then
 * "Link", instead of the filename. Everything else falls back to filename.
 *
 * `language` picks the Arabic (auto-translated, see main.py's
 * _translate_ar_safe) or English field; a null/blank Arabic value (not yet
 * translated, or translation failed) falls back to the English one rather
 * than showing nothing. The raw filename fallback has no Arabic
 * equivalent — it's a real filename, not admin-authored text — so it's
 * language-independent.
 */
export function resolveDisplayName(
  item: Nameable | null | undefined,
  language: 'en' | 'ar' = 'en',
): string {
  if (!item) return '';
  const name =
    (language === 'ar' ? item.display_name_ar?.trim() : null) || item.display_name?.trim();
  if (name) return name;

  if (item.media_type === 'link') {
    const description =
      (language === 'ar' ? item.description_ar?.trim() : null) || item.description?.trim();
    return description || 'Link';
  }

  return item.filename;
}

@Pipe({ name: 'displayName' })
export class DisplayNamePipe implements PipeTransform {
  transform(item: Nameable | null | undefined, language: 'en' | 'ar' = 'en'): string {
    return resolveDisplayName(item, language);
  }
}
