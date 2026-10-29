import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { VideoItem } from '../../../core/models/video.models';
import { LanguageService } from '../../../core/services/language.service';
import { VideosService } from '../../../core/services/videos.service';
import { extractYoutubeId } from '../../../shared/utils/youtube';

interface VideoCategoryGroup {
  categoryId: string;
  categoryName: string;
  videos: VideoItem[];
}

@Component({
  selector: 'app-videos-page',
  imports: [FormsModule],
  templateUrl: './videos-page.html',
  styleUrl: './videos-page.scss',
})
export class VideosPage implements OnInit {
  private readonly videosService = inject(VideosService);
  private readonly sanitizer = inject(DomSanitizer);
  readonly lang = inject(LanguageService);

  readonly videos = signal<VideoItem[]>([]);
  readonly isLoading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly searchQuery = signal('');

  private readonly embedUrlCache = new Map<string, SafeResourceUrl | null>();

  readonly filteredVideos = computed(() => {
    const query = this.searchQuery().trim().toLowerCase();
    if (!query) return this.videos();
    return this.videos().filter((v) => this.title(v).toLowerCase().includes(query));
  });

  readonly groupedVideos = computed<VideoCategoryGroup[]>(() => {
    const groups = new Map<string, VideoCategoryGroup>();
    for (const video of this.filteredVideos()) {
      const existing = groups.get(video.category_id);
      if (existing) {
        existing.videos.push(video);
      } else {
        groups.set(video.category_id, {
          categoryId: video.category_id,
          categoryName: video.category_name,
          videos: [video],
        });
      }
    }
    return [...groups.values()].sort((a, b) => a.categoryName.localeCompare(b.categoryName));
  });

  ngOnInit(): void {
    this.videosService.list().subscribe({
      next: (videos) => {
        this.videos.set(videos);
        this.isLoading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading.set(false);
        const detail = err.error?.detail;
        this.errorMessage.set(
          typeof detail === 'string' ? detail : this.lang.translate('videos.couldNotLoad'),
        );
      },
    });
  }

  onSearchChange(value: string): void {
    this.searchQuery.set(value);
  }

  title(video: VideoItem): string {
    const name = this.lang.lang() === 'ar' ? video.display_name_ar?.trim() : video.display_name?.trim();
    return name || video.display_name?.trim() || this.description(video) || this.lang.translate('videos.untitled');
  }

  description(video: VideoItem): string {
    return this.lang.lang() === 'ar'
      ? video.description_ar?.trim() || video.description
      : video.description;
  }

  /** Cached so the sanitizer/trust call (and the embed iframe) isn't
   * re-created on every change-detection pass for the same video. */
  embedUrl(video: VideoItem): SafeResourceUrl | null {
    if (this.embedUrlCache.has(video.id)) {
      return this.embedUrlCache.get(video.id)!;
    }
    const videoId = extractYoutubeId(video.url);
    const result = videoId
      ? this.sanitizer.bypassSecurityTrustResourceUrl(`https://www.youtube-nocookie.com/embed/${videoId}`)
      : null;
    this.embedUrlCache.set(video.id, result);
    return result;
  }
}
