import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { LanguageService } from '../../../core/services/language.service';

@Component({
  selector: 'app-superadmin-nav',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './superadmin-nav.html',
  styleUrl: './superadmin-nav.scss',
})
export class SuperadminNav {
  readonly lang = inject(LanguageService);
}
