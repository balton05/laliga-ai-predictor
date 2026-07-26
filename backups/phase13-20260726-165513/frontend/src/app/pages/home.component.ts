import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { teamStadium } from '../core/team-assets';
import { DataService } from '../data.service';
import { Health, Prediction, Simulation } from '../models';
import { TeamLogoComponent } from '../shared/team-logo.component';

@Component({
  standalone: true,
  imports: [RouterLink, TeamLogoComponent],
  template: `
    <section class="page home-page">
      <div class="hero-copy">
        <p class="eyebrow">INTELIGENCIA DEPORTIVA · PRETEMPORADA</p>
        <h1>LaLiga 2026/27,<br><span>predicha partido a partido.</span></h1>
        <p class="hero-description">
          Probabilidades 1X2, marcadores esperados y 50,000 temporadas
          simuladas con información disponible antes de cada encuentro.
        </p>
        <div class="hero-actions">
          <a class="button button-primary" routerLink="/pronosticos">
            Ver pronósticos <span>→</span>
          </a>
          <a class="button button-ghost" routerLink="/simulacion">
            Explorar simulación
          </a>
        </div>
      </div>

      @if (featured(); as match) {
        <article
          class="featured-match featured-match--stadium card"
          [style.background-image]="stadiumBackground(match.home_team)"
        >
          <div class="featured-match__overlay">
          <div class="card-heading">
            <span>Partido destacado</span>
            <span class="matchday-chip">J{{ match.matchday }}</span>
          </div>
          <div class="versus">
            <div class="team">
              <app-team-logo [teamName]="match.home_team" [size]="66" />
              <strong>{{ match.home_team }}</strong>
              <small>Local</small>
            </div>
            <div class="score-prediction">
              <strong>{{ match.predicted_score }}</strong>
              <small>marcador más probable</small>
            </div>
            <div class="team">
              <app-team-logo [teamName]="match.away_team" [size]="66" />
              <strong>{{ match.away_team }}</strong>
              <small>Visitante</small>
            </div>
          </div>
          <div class="probability-strip">
            <div
              class="home"
              [style.width.%]="match.probability_home * 100"
            ></div>
            <div
              class="draw"
              [style.width.%]="match.probability_draw * 100"
            ></div>
            <div
              class="away"
              [style.width.%]="match.probability_away * 100"
            ></div>
          </div>
          <div class="probability-labels">
            <span><b>1</b> {{ pct(match.probability_home) }}</span>
            <span><b>X</b> {{ pct(match.probability_draw) }}</span>
            <span><b>2</b> {{ pct(match.probability_away) }}</span>
          </div>
          <div class="match-meta">
            <span>Ensemble deportivo</span>
            <span>{{ match.expected_home_goals.toFixed(2) }}–{{ match.expected_away_goals.toFixed(2) }} xG</span>
          </div>
          </div>
        </article>
      } @else {
        <div class="featured-match card skeleton-panel"></div>
      }

      <div class="metric-grid">
        <article class="metric-card card cyan">
          <div class="metric-icon">▦</div>
          <div>
            <span>Partidos pendientes</span>
            <strong>{{ health()?.fixtures ?? 380 }}</strong>
            <small>Calendario completo</small>
          </div>
        </article>
        <article class="metric-card card yellow">
          <div class="metric-icon">★</div>
          <div>
            <span>Favorito al título</span>
            <strong>{{ champion().team }}</strong>
            <small>{{ pct(champion().champion_probability) }} de probabilidad</small>
          </div>
        </article>
        <article class="metric-card card pink">
          <div class="metric-icon">↓</div>
          <div>
            <span>Mayor riesgo de descenso</span>
            <strong>{{ relegation().team }}</strong>
            <small>{{ pct(relegation().relegation_probability) }} de probabilidad</small>
          </div>
        </article>
        <article class="metric-card card purple">
          <div class="metric-icon">≈</div>
          <div>
            <span>Simulaciones</span>
            <strong>{{ compact(health()?.simulations ?? 50000) }}</strong>
            <small>Monte Carlo reproducible</small>
          </div>
        </article>
      </div>

      <div class="home-lower">
        <article class="card insight-card">
          <div>
            <p class="eyebrow">QUÉ HACE DIFERENTE AL MODELO</p>
            <h2>No adivina un resultado. <span>Cuantifica la incertidumbre.</span></h2>
          </div>
          <div class="insight-list">
            <div><span>01</span><p><b>Sin fuga de información</b><small>Solo datos conocidos antes del partido.</small></p></div>
            <div><span>02</span><p><b>Validación temporal</b><small>2025/26 se usó una sola vez como prueba final.</small></p></div>
            <div><span>03</span><p><b>Ensemble calibrado</b><small>Random Forest, Poisson y regresión logística.</small></p></div>
          </div>
        </article>
      </div>
    </section>
  `,
})
export class HomeComponent {
  private readonly data = inject(DataService);
  readonly predictions = signal<Prediction[]>([]);
  readonly simulation = signal<Simulation[]>([]);
  readonly health = signal<Health | null>(null);
  private readonly defaultChampion: Simulation = {
    team_id: 'barcelona',
    team: 'FC Barcelona',
    simulations: 50000,
    expected_points: 74.7,
    points_p05: 62,
    points_p95: 87,
    expected_position: 1.8,
    champion_probability: 0.53748,
    top4_probability: 0.96314,
    europe_top7_probability: 0.99478,
    relegation_probability: 0,
  };
  private readonly defaultRelegation: Simulation = {
    team_id: 'deportivo',
    team: 'RC Deportivo',
    simulations: 50000,
    expected_points: 39.3,
    points_p05: 27,
    points_p95: 52,
    expected_position: 15.8,
    champion_probability: 0,
    top4_probability: 0.006,
    europe_top7_probability: 0.026,
    relegation_probability: 0.5004,
  };
  readonly featured = computed(
    () =>
      this.predictions().find(
        (match) => match.home_team === 'FC Barcelona',
      ) ?? this.predictions()[0],
  );
  readonly champion = computed(() =>
    [...this.simulation()].sort(
      (a, b) => b.champion_probability - a.champion_probability,
    )[0] ?? this.defaultChampion,
  );
  readonly relegation = computed(() =>
    [...this.simulation()].sort(
      (a, b) => b.relegation_probability - a.relegation_probability,
    )[0] ?? this.defaultRelegation,
  );

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    const [predictions, simulation, health] = await Promise.all([
      this.data.predictions(),
      this.data.simulation(),
      this.data.health(),
    ]);
    this.predictions.set(predictions);
    this.simulation.set(simulation);
    this.health.set(health);
  }

  pct(value: number): string {
    return `${(value * 100).toFixed(1)}%`;
  }

  compact(value: number): string {
    return new Intl.NumberFormat('es-PE', {
      notation: 'compact',
      maximumFractionDigits: 0,
    }).format(value);
  }

  stadiumBackground(teamName: string): string {
    return `url("${teamStadium(teamName)}"), url("assets/stadiums/default-stadium.svg")`;
  }
}
