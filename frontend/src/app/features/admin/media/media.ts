import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MediaUploadResponse } from '../../../core/models/media.models';
import { MediaService } from '../../../core/services/media.service';

type ItemStatus = 'uploading' | 'done' | 'error';

interface MediaItem {
  id: string;
  filename: string;
  description: string;
  mediaType?: string;
  status: ItemStatus;
  errorMessage?: string;
}

const ALLOWED_EXTENSIONS = ['.mp4', '.mov', '.webm', '.jpg', '.jpeg', '.png', '.gif', '.webp'];

@Component({
  selector: 'app-media',
  imports: [ReactiveFormsModule],
  templateUrl: './media.html',
  styleUrl: './media.scss',
})
export class Media {
  private readonly mediaService = inject(MediaService);
  private readonly fb = inject(FormBuilder);

  readonly selectedFile = signal<File | null>(null);
  readonly uploads = signal<MediaItem[]>([]);
  readonly isLoading = signal(false);
  readonly fileError = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    description: ['', [Validators.required, Validators.minLength(3)]],
  });

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = '';

    if (!file) {
      return;
    }

    if (!this.hasAllowedExtension(file.name)) {
      this.fileError.set('Unsupported file type. Allowed: MP4, MOV, WebM, JPG, PNG, GIF, WebP.');
      this.selectedFile.set(null);
      return;
    }

    this.fileError.set(null);
    this.selectedFile.set(file);
  }

  submit(): void {
    const file = this.selectedFile();

    if (!file) {
      this.fileError.set('Please select a file.');
      return;
    }

    if (this.form.invalid || this.isLoading()) {
      this.form.markAllAsTouched();
      return;
    }

    const { description } = this.form.getRawValue();
    const itemId = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

    this.uploads.update((items) => [
      { id: itemId, filename: file.name, description, status: 'uploading' },
      ...items,
    ]);

    this.isLoading.set(true);
    this.selectedFile.set(null);
    this.form.reset();

    this.mediaService.upload(file, description).subscribe({
      next: (res: MediaUploadResponse) => {
        this.isLoading.set(false);
        this.uploads.update((items) =>
          items.map((item) =>
            item.id === itemId
              ? { ...item, status: 'done', mediaType: res.media_type }
              : item
          )
        );
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading.set(false);
        const detail = err.error?.detail;
        const message = typeof detail === 'string' ? detail : 'Upload failed. Please try again.';
        this.uploads.update((items) =>
          items.map((item) =>
            item.id === itemId ? { ...item, status: 'error', errorMessage: message } : item
          )
        );
      },
    });
  }

  mediaIcon(item: MediaItem): string {
    const type = item.mediaType ?? '';
    if (type.startsWith('video') || this.isVideoExtension(item.filename)) {
      return 'play_circle';
    }
    return 'image';
  }

  private isVideoExtension(filename: string): boolean {
    const lower = filename.toLowerCase();
    return ['.mp4', '.mov', '.webm'].some((ext) => lower.endsWith(ext));
  }

  private hasAllowedExtension(filename: string): boolean {
    const lower = filename.toLowerCase();
    return ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext));
  }
}
