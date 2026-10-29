import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Category } from '../../../core/models/category.models';
import { CategoriesService } from '../../../core/services/categories.service';

@Component({
  selector: 'app-categories',
  imports: [FormsModule],
  templateUrl: './categories.html',
  styleUrl: './categories.scss',
})
export class Categories implements OnInit {
  private readonly categoriesService = inject(CategoriesService);

  readonly categories = signal<Category[]>([]);
  readonly loadError = signal<string | null>(null);
  readonly newName = signal('');
  readonly isAdding = signal(false);
  readonly addError = signal<string | null>(null);
  readonly addSuccess = signal<string | null>(null);

  ngOnInit(): void {
    this.loadCategories();
  }

  add(): void {
    const name = this.newName().trim();
    if (!name || this.isAdding()) return;

    this.isAdding.set(true);
    this.addError.set(null);
    this.addSuccess.set(null);

    this.categoriesService.create(name).subscribe({
      next: (category) => {
        this.categories.update((items) => [...items, category]);
        this.newName.set('');
        this.isAdding.set(false);
        this.addSuccess.set(`Category "${category.name}" created.`);
      },
      error: (err: HttpErrorResponse) => {
        this.isAdding.set(false);
        if (err.status === 409) {
          this.addError.set(`A category named "${name}" already exists.`);
        } else {
          const detail = err.error?.detail;
          this.addError.set(typeof detail === 'string' ? detail : 'Could not create category.');
        }
      },
    });
  }

  private loadCategories(): void {
    this.categoriesService.list().subscribe({
      next: (cats) => {
        this.categories.set(cats);
        this.loadError.set(null);
      },
      error: (err: HttpErrorResponse) => {
        const detail = err.error?.detail;
        this.loadError.set(typeof detail === 'string' ? detail : 'Could not load categories.');
      },
    });
  }
}
