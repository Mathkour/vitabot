import { Component, ElementRef, HostListener, ViewChild, input, output, signal } from '@angular/core';

export interface DropdownOption {
  value: string;
  label: string;
}

@Component({
  selector: 'app-dropdown-select',
  templateUrl: './dropdown-select.html',
  styleUrl: './dropdown-select.scss',
})
export class DropdownSelect {
  readonly options = input.required<DropdownOption[]>();
  readonly value = input.required<string>();
  readonly disabled = input<boolean>(false);
  readonly placeholder = input<string>('Select...');

  readonly valueChange = output<string>();

  readonly isOpen = signal(false);

  @ViewChild('root') private root?: ElementRef<HTMLDivElement>;

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.isOpen()) return;
    const el = this.root?.nativeElement;
    if (el && !el.contains(event.target as Node)) {
      this.isOpen.set(false);
    }
  }

  @HostListener('document:keydown.escape')
  onEscapeKey(): void {
    this.isOpen.set(false);
  }

  toggle(): void {
    if (this.disabled()) return;
    this.isOpen.update((open) => !open);
  }

  select(option: DropdownOption): void {
    this.valueChange.emit(option.value);
    this.isOpen.set(false);
  }

  selectedLabel(): string {
    return this.options().find((o) => o.value === this.value())?.label ?? this.placeholder();
  }
}
