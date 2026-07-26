import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  teamAssetByName,
  teamStadium,
} from '../core/team-assets';
import { DataService } from '../data.service';
import { Fixture } from '../models';
import { TeamLogoComponent } from '../shared/team-logo.component';

@Component({
  standalone: true,
  imports: [FormsModule, TeamLogoComponent],
  template: `
    <section class="page">
      <div class="page-heading">
        <div>
          <p class="eyebrow">380 ENCUENTROS</p>
          <h1>Calendario 2026/27</h1>
          <p>Consulta cada jornada del calendario oficial incorporado al modelo.</p>
        </div>
        <label class="matchday-selector">
          <span>Jornada</span>
          <select [(ngModel)]="matchday">
            @for (day of matchdays; track day) {
              <option [ngValue]="day">{{ day }}</option>
            }
          </select>
        </label>
      </div>

      <div class="calendar-header card">
        <button type="button" (click)="previous()" [disabled]="matchday === 1">←</button>
        <div><small>Jornada</small><strong>{{ matchday }}</strong><span>{{ dateRange() }}</span></div>
        <button type="button" (click)="next()" [disabled]="matchday === 38">→</button>
      </div>

      <div class="fixture-list">
        @for (fixture of currentFixtures(); track fixture.fixture_id) {
          <article
            class="fixture-row fixture-row--stadium card"
            [style.background-image]="stadiumBackground(fixture.home_team)"
          >
            <div class="fixture-row__overlay">
              <div class="fixture-date">
                <strong>{{ day(fixture.reference_date) }}</strong>
                <span>{{ shortDate(fixture.reference_date) }}</span>
              </div>
              <div class="fixture-team home-side">
                <strong>{{ fixture.home_team }}</strong>
                <app-team-logo [teamName]="fixture.home_team" [size]="42" />
              </div>
              <div class="fixture-versus">
                <span>{{ fixture.kickoff_time || 'Por confirmar' }}</span>
                <b>vs.</b>
                <small>{{ stadiumName(fixture.home_team) }}</small>
              </div>
              <div class="fixture-team">
                <app-team-logo [teamName]="fixture.away_team" [size]="42" />
                <strong>{{ fixture.away_team }}</strong>
              </div>
              <span class="status-chip">
                {{ statusLabel(fixture.status) }}
              </span>
            </div>
          </article>
        } @empty {
          <div class="empty-state card">
            <strong>Cargando calendario</strong>
            <span>Estamos preparando los partidos de esta jornada.</span>
          </div>
        }
      </div>
    </section>
  `,
})
export class CalendarComponent {
  private readonly data = inject(DataService);
  readonly fixtures = signal<Fixture[]>([]);
  matchday = 1;
  readonly matchdays = Array.from({ length: 38 }, (_, index) => index + 1);
  readonly currentFixtures = computed(() =>
    this.fixtures().filter((fixture) => fixture.matchday === this.matchday),
  );

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.fixtures.set(await this.data.fixtures());
  }

  previous(): void {
    this.matchday = Math.max(1, this.matchday - 1);
  }

  next(): void {
    this.matchday = Math.min(38, this.matchday + 1);
  }

  dateRange(): string {
    const fixtures = this.currentFixtures();
    if (!fixtures.length) return 'Fechas por confirmar';
    const dates = fixtures.map((item) => new Date(`${item.reference_date}T12:00:00`));
    const min = new Date(Math.min(...dates.map((date) => date.getTime())));
    const max = new Date(Math.max(...dates.map((date) => date.getTime())));
    const formatter = new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'short' });
    return min.getTime() === max.getTime()
      ? formatter.format(min)
      : `${formatter.format(min)} – ${formatter.format(max)}`;
  }

  day(value: string): string {
    return new Intl.DateTimeFormat('es-ES', { weekday: 'short' })
      .format(new Date(`${value}T12:00:00`))
      .replace('.', '')
      .toUpperCase();
  }

  shortDate(value: string): string {
    return new Intl.DateTimeFormat('es-ES', {
      day: '2-digit',
      month: 'short',
    }).format(new Date(`${value}T12:00:00`));
  }

  stadiumBackground(teamName: string): string {
    return `url("${teamStadium(teamName)}"), url("assets/stadiums/default-stadium.svg")`;
  }

  stadiumName(teamName: string): string {
    return teamAssetByName(teamName)?.stadiumName ?? 'Estadio por confirmar';
  }

  statusLabel(status: string): string {
    return {
      scheduled: 'Programado',
      finished: 'Finalizado',
      postponed: 'Aplazado',
    }[status] ?? status;
  }
}
