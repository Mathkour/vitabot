/** Extracts the video ID from a youtube.com/watch?v= or youtu.be/ URL, or null if not a match. */
export function extractYoutubeId(url: string): string | null {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, '');

    if (host === 'youtu.be') {
      return parsed.pathname.slice(1).split('/')[0] || null;
    }

    if (host === 'youtube.com' && parsed.pathname === '/watch') {
      return parsed.searchParams.get('v');
    }

    return null;
  } catch {
    return null;
  }
}
