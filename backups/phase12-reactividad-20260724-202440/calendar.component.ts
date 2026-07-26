import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DataService } from '../data.service';
import { Fixture } from '../models';

@Component({
  standalone: true,
  imports: [FormsModule],
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
          <article class="fixture-row card">
            <div class="fixture-date">
              <strong>{{ day(fixture.reference_date) }}</strong>
              <span>{{ shortDate(fixture.reference_date) }}</span>
            </div>
            <div class="fixture-team home-side">
              <strong>{{ fixture.home_team }}</strong>
              <span class="mini-crest">{{ initials(fixture.home_team) }}</span>
            </div>
            <div class="fixture-versus">
              <span>{{ fixture.kickoff_time || 'Por confirmar' }}</span>
              <b>vs.</b>
            </div>
            <div class="fixture-team">
              <span class="mini-crest away">{{ initials(fixture.away_team) }}</span>
              <strong>{{ fixture.away_team }}</strong>
            </div>
            <span class="status-chip">{{ fixture.status === 'scheduled' ? 'Programado' : fixture.status }}</span>
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

  initials(team: string): string {
    return team
      .replace(/\b(FC|CF|RC|RCD|Club|de|del)\b/gi, '')
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0])
      .join('')
      .toUpperCase();
  }
}
