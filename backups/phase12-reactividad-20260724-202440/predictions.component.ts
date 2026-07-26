import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DataService } from '../data.service';
import { Prediction } from '../models';

@Component({
  standalone: true,
  imports: [FormsModule],
  template: `
    <section class="page">
      <div class="page-heading">
        <div>
          <p class="eyebrow">MODELO 1X2</p>
          <h1>Pronósticos por partido</h1>
          <p>Explora las probabilidades, el marcador esperado y la confianza del ensemble.</p>
        </div>
        <div class="page-count"><strong>{{ filtered().length }}</strong><span>partidos</span></div>
      </div>

      <div class="filters card">
        <label>
          <span>Buscar equipo</span>
          <input
            type="search"
            placeholder="Barcelona, Betis..."
            [(ngModel)]="search"
          >
        </label>
        <label>
          <span>Jornada</span>
          <select [(ngModel)]="matchday">
            <option [ngValue]="0">Todas</option>
            @for (day of matchdays; track day) {
              <option [ngValue]="day">Jornada {{ day }}</option>
            }
          </select>
        </label>
        <div class="legend">
          <span><i class="home"></i> Local</span>
          <span><i class="draw"></i> Empate</span>
          <span><i class="away"></i> Visitante</span>
        </div>
      </div>

      @if (loading()) {
        <div class="loading-grid">
          @for (item of [1,2,3,4,5,6]; track item) {
            <div class="card skeleton-panel"></div>
          }
        </div>
      } @else {
        <div class="prediction-grid">
          @for (match of filtered(); track match.fixture_id) {
            <article class="prediction-card card">
              <div class="prediction-top">
                <span>Jornada {{ match.matchday }}</span>
                <span class="confidence" [class.high]="match.confidence === 'high'">
                  {{ confidenceLabel(match.confidence) }}
                </span>
              </div>
              <div class="prediction-teams">
                <div><span class="mini-crest">{{ initials(match.home_team) }}</span><strong>{{ match.home_team }}</strong></div>
                <span class="predicted-score">{{ match.predicted_score }}</span>
                <div><span class="mini-crest away">{{ initials(match.away_team) }}</span><strong>{{ match.away_team }}</strong></div>
              </div>
              <div class="probability-columns">
                <div [class.winner]="match.predicted_ftr === 'H'">
                  <span>1</span><strong>{{ pct(match.probability_home) }}</strong>
                </div>
                <div [class.winner]="match.predicted_ftr === 'D'">
                  <span>X</span><strong>{{ pct(match.probability_draw) }}</strong>
                </div>
                <div [class.winner]="match.predicted_ftr === 'A'">
                  <span>2</span><strong>{{ pct(match.probability_away) }}</strong>
                </div>
              </div>
              <div class="probability-strip compact">
                <div class="home" [style.width.%]="match.probability_home * 100"></div>
                <div class="draw" [style.width.%]="match.probability_draw * 100"></div>
                <div class="away" [style.width.%]="match.probability_away * 100"></div>
              </div>
              <div class="prediction-footer">
                <span>xG {{ match.expected_home_goals.toFixed(2) }}–{{ match.expected_away_goals.toFixed(2) }}</span>
                <span>{{ match.market_odds_available ? 'Con mercado' : 'Solo deportivo' }}</span>
              </div>
            </article>
          } @empty {
            <div class="empty-state card">
              <strong>No encontramos partidos</strong>
              <span>Prueba con otro equipo o jornada.</span>
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class PredictionsComponent {
  private readonly data = inject(DataService);
  readonly predictions = signal<Prediction[]>([]);
  readonly loading = signal(true);
  search = '';
  matchday = 1;
  readonly matchdays = Array.from({ length: 38 }, (_, index) => index + 1);
  readonly filtered = computed(() => {
    const query = this.search.toLowerCase().trim();
    return this.predictions().filter(
      (match) =>
        (this.matchday === 0 || match.matchday === this.matchday) &&
        (!query ||
          match.home_team.toLowerCase().includes(query) ||
          match.away_team.toLowerCase().includes(query)),
    );
  });

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.predictions.set(await this.data.predictions());
    this.loading.set(false);
  }

  pct(value: number): string {
    return `${(value * 100).toFixed(1)}%`;
  }

  confidenceLabel(value: string): string {
    return { high: 'Alta', medium: 'Media', low: 'Baja' }[value] ?? value;
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
