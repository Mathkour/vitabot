import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { BrandFooter } from '../../shared/brand-footer/brand-footer';
import { Topbar } from '../topbar/topbar';

@Component({
  selector: 'app-client-layout',
  imports: [RouterOutlet, Topbar, BrandFooter],
  templateUrl: './client-layout.html',
  styleUrl: './client-layout.scss',
})
export class ClientLayout {}
