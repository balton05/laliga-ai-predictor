import { Component, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { DataService } from './data.service';

@Component({
  selector: '[data-laliga-root]',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  template: `
    <div class="app-shell">
      <aside class="sidebar" [class.sidebar-open]="menuOpen()">
        <a class="brand" routerLink="/" (click)="closeMenu()">
          <img
            class="brand-logo"
            src="assets/logos/laliga-ai-predictor-logo.png"
            alt="LaLiga AI Predictor"
            (error)="hideBrokenImage($event)"
          >
          <span class="brand-fallback">
            <span class="brand-mark">AI</span>
            <span>
              <strong>LaLiga</strong>
              <small>Predictor 26/27</small>
            </span>
          </span>
        </a>

        <nav aria-label="Navegación principal">
          @for (item of navItems; track item.path) {
            <a
              [routerLink]="item.path"
              routerLinkActive="active"
              [routerLinkActiveOptions]="{ exact: item.path === '/' }"
              (click)="closeMenu()"
            >
              <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
              {{ item.label }}
            </a>
          }
        </nav>

        <div class="model-note">
          <span class="pulse-dot"></span>
          <div>
            <strong>Ensemble deportivo</strong>
            <small>55% RF · 35% Poisson · 10% LR</small>
          </div>
        </div>
      </aside>

      @if (menuOpen()) {
        <button
          class="scrim"
          aria-label="Cerrar menú"
          (click)="closeMenu()"
        ></button>
      }

      <section class="workspace">
        <header class="topbar">
          <button
            class="menu-button"
            type="button"
            aria-label="Abrir menú"
            (click)="menuOpen.set(true)"
          >
            ☰
          </button>
          <div class="season-pill">Temporada 2026/27</div>
          <div class="data-status" [class.demo]="data.mode() === 'demo'">
            <span></span>
            {{ data.modeLabel() }}
          </div>
        </header>

        <main class="content">
          <router-outlet />
        </main>

        <footer>
          <span>LaLiga AI Predictor · Fase 12</span>
          <span>Las probabilidades son estimaciones, no certezas.</span>
        </footer>
      </section>
    </div>
  `,
})
export class AppComponent {
  readonly data = inject(DataService);
  readonly menuOpen = signal(false);
  readonly navItems = [
    { path: '/', label: 'Resumen', icon: '⌂' },
    { path: '/pronosticos', label: 'Pronósticos', icon: '◎' },
    { path: '/calendario', label: 'Calendario', icon: '▦' },
    { path: '/clasificacion', label: 'Clasificación', icon: '≡' },
    { path: '/simulacion', label: 'Simulación', icon: '↗' },
    { path: '/equipos', label: 'Equipos', icon: '◇' },
  ];

  closeMenu(): void {
    this.menuOpen.set(false);
  }

  hideBrokenImage(event: Event): void {
    const image = event.currentTarget as HTMLImageElement;
    image.style.display = 'none';
    const fallback = image.nextElementSibling as HTMLElement | null;
    if (fallback) fallback.style.display = 'flex';
  }
}
