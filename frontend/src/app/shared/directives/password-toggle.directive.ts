import { Directive, ElementRef, OnInit, Renderer2, inject } from '@angular/core';
import { LanguageService } from '../../core/services/language.service';

/**
 * Drop-in show/hide toggle for a password <input> — wraps it with a
 * positioned eye-icon button that flips the input's type between
 * "password" and "text". Built as a directive rather than a wrapper
 * component so every existing `<input type="password" formControlName="...">`
 * only needs one attribute added, no template restructuring.
 */
@Directive({
  selector: 'input[appPasswordToggle]',
})
export class PasswordToggleDirective implements OnInit {
  private readonly el = inject(ElementRef<HTMLInputElement>);
  private readonly renderer = inject(Renderer2);
  private readonly lang = inject(LanguageService);

  private button!: HTMLButtonElement;
  private icon!: HTMLSpanElement;

  ngOnInit(): void {
    const input = this.el.nativeElement;
    const parent = this.renderer.parentNode(input);

    const wrapper = this.renderer.createElement('div');
    this.renderer.addClass(wrapper, 'password-toggle-wrap');
    this.renderer.insertBefore(parent, wrapper, input);
    this.renderer.appendChild(wrapper, input);
    this.renderer.addClass(input, 'password-toggle-input');

    this.icon = this.renderer.createElement('span');
    this.renderer.addClass(this.icon, 'material-symbols-outlined');
    this.renderer.appendChild(this.icon, this.renderer.createText('visibility'));

    this.button = this.renderer.createElement('button');
    this.renderer.setAttribute(this.button, 'type', 'button');
    this.renderer.setAttribute(this.button, 'tabindex', '-1');
    this.renderer.addClass(this.button, 'password-toggle-btn');
    this.renderer.setAttribute(this.button, 'aria-label', this.lang.translate('common.showPassword'));
    this.renderer.appendChild(this.button, this.icon);
    this.renderer.listen(this.button, 'click', () => this.toggle());

    this.renderer.appendChild(wrapper, this.button);
  }

  private toggle(): void {
    const input = this.el.nativeElement;
    const showing = input.type === 'text';
    this.renderer.setAttribute(input, 'type', showing ? 'password' : 'text');
    this.renderer.setProperty(this.icon, 'textContent', showing ? 'visibility' : 'visibility_off');
    this.renderer.setAttribute(
      this.button,
      'aria-label',
      this.lang.translate(showing ? 'common.showPassword' : 'common.hidePassword'),
    );
  }
}
