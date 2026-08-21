import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import {
  TeamAsset,
  teamAssetByName,
  teamAssetBySlug,
} from '../core/team-assets';
import { DataService } from '../data.service';
import { Fixture, Prediction, Simulation, Standing } from '../models';
import { TeamLogoComponent } from '../shared/team-logo.component';

@Component({
  standalone: true,
  imports: [RouterLink, TeamLogoComponent],
  template: `
    <section class="page team-detail-page">
      @if (team; as selectedTeam) {
        <a class="back-link" routerLink="/equipos">← Volver a equipos</a>

        <header
          class="team-hero card"
        >
          <img
            class="team-hero__stadium"
            [src]="stadiumImage(selectedTeam)"
            [alt]="'Estadio ' + selectedTeam.stadiumName"
            (error)="useStadiumFallback($event)"
          />
          <div class="team-hero__overlay">
            <app-team-logo [teamName]="selectedTeam.name" [size]="112" />
            <div>
              <p class="eyebrow">FICHA DEL CLUB</p>
              <h1>{{ selectedTeam.name }}</h1>
              <p>{{ selectedTeam.city }} · {{ selectedTeam.stadiumName }}</p>
            </div>
          </div>
        </header>

        <div class="team-kpis">
          <article class="card">
            <span>Posición media</span>
            <strong>{{ position() }}</strong>
          </article>
          <article class="card">
            <span>Puntos esperados</span>
            <strong>{{ points() }}</strong>
          </article>
          <article class="card">
            <span>Prob. de campeón</span>
            <strong>{{ pct(simulation()?.champion_probability) }}</strong>
          </article>
          <article class="card danger-kpi">
            <span>Riesgo de descenso</span>
            <strong>{{ pct(simulation()?.relegation_probability) }}</strong>
          </article>
        </div>

        <div class="team-detail-grid">
          <article class="card team-zone-card">
            <div class="card-heading">
              <span>PROYECCIÓN DE ZONAS</span>
              <span>50,000 simulaciones</span>
            </div>
            <div class="zone-probabilities">
              <div>
                <span>Campeón</span>
                <strong>{{ pct(simulation()?.champion_probability) }}</strong>
              </div>
              <div>
                <span>Top 4</span>
                <strong>{{ pct(simulation()?.top4_probability) }}</strong>
              </div>
              <div>
                <span>Top 7</span>
                <strong>{{ pct(simulation()?.europe_top7_probability) }}</strong>
              </div>
              <div>
                <span>Descenso</span>
                <strong class="danger">{{ pct(simulation()?.relegation_probability) }}</strong>
              </div>
            </div>
          </article>

          <article class="card team-matches-card">
            <div class="card-heading">
              <span>PRÓXIMOS PARTIDOS</span>
              <span>{{ nextFixtures().length }} encuentros</span>
            </div>
            <div class="team-match-list">
              @for (fixture of nextFixtures(); track fixture.fixture_id) {
                <div>
                  <span>J{{ fixture.matchday }}</span>
                  <app-team-logo [teamName]="opponent(fixture)" [size]="34" />
                  <strong>{{ opponent(fixture) }}</strong>
                  <b>{{ isHomeFixture(fixture) ? 'Local' : 'Visitante' }}</b>
                </div>
              } @empty {
                <p class="muted-message">No hay partidos disponibles.</p>
              }
            </div>
          </article>
        </div>

        <article class="card team-predictions-card">
          <div class="card-heading">
            <span>PRÓXIMOS PRONÓSTICOS</span>
            <a routerLink="/pronosticos">Ver todos →</a>
          </div>
          <div class="team-predictions-grid">
            @for (prediction of nextPredictions(); track prediction.fixture_id) {
              <div>
                <span>J{{ prediction.matchday }}</span>
                <strong>{{ prediction.home_team }} vs. {{ prediction.away_team }}</strong>
                <b>{{ prediction.predicted_score }}</b>
                <small>
                  1 {{ pct(prediction.probability_home) }} ·
                  X {{ pct(prediction.probability_draw) }} ·
                  2 {{ pct(prediction.probability_away) }}
                </small>
              </div>
            }
          </div>
        </article>
      } @else {
        <div class="empty-state card">
          <strong>Equipo no encontrado</strong>
          <a routerLink="/equipos">Volver al listado</a>
        </div>
      }
    </section>
  `,
  styles: [`
    .team-hero {
      position: relative;
      isolation: isolate;
      background: #07101f;
    }

    .team-hero__stadium {
      position: absolute;
      z-index: 0;
      inset: 0;
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
      object-position: center;
    }

    .team-hero::after {
      position: absolute;
      z-index: 1;
      inset: 0;
      background: linear-gradient(
        100deg,
        rgba(5, 9, 20, 0.94),
        rgba(5, 9, 20, 0.48),
        rgba(5, 9, 20, 0.78)
      );
      content: '';
      pointer-events: none;
    }

    .team-hero__overlay {
      position: relative;
      z-index: 2;
    }
  `],
})
export class TeamDetailComponent {
  private readonly data = inject(DataService);
  private readonly route = inject(ActivatedRoute);
  readonly team: TeamAsset | undefined = teamAssetBySlug(
    this.route.snapshot.paramMap.get('slug') ?? '',
  );
  readonly standings = signal<Standing[]>([]);
  readonly simulations = signal<Simulation[]>([]);
  readonly fixtures = signal<Fixture[]>([]);
  readonly predictions = signal<Prediction[]>([]);

  readonly standing = computed(() =>
    this.standings().find((row) => row.team_id === this.team?.teamId),
  );
  readonly simulation = computed(() =>
    this.simulations().find((row) => row.team_id === this.team?.teamId),
  );
  readonly nextFixtures = computed(() => {
    const pendingFixtureIds = new Set(
      this.predictions().map((prediction) => prediction.fixture_id),
    );

    return this.fixtures()
      .filter(
        (fixture) =>
          pendingFixtureIds.has(fixture.fixture_id) &&
          (fixture.home_team_id === this.team?.teamId ||
            fixture.away_team_id === this.team?.teamId),
      )
      .slice(0, 5);
  });
  readonly nextPredictions = computed(() =>
    this.predictions()
      .filter(
        (prediction) =>
          this.belongsToTeam(prediction.home_team) ||
          this.belongsToTeam(prediction.away_team),
      )
      .slice(0, 4),
  );

  constructor() {
    if (this.team) void this.load();
  }

  private async load(): Promise<void> {
    const [standings, simulations, fixtures, predictions] = await Promise.all([
      this.data.standings(),
      this.data.simulation(),
      this.data.fixtures(),
      this.data.predictions(),
    ]);
    this.standings.set(standings);
    this.simulations.set(simulations);
    this.fixtures.set(fixtures);
    this.predictions.set(predictions);
  }

  position(): string {
    const value =
      this.standing()?.position ?? this.simulation()?.expected_position;
    return value === undefined || value === null ? '—' : value.toFixed(1);
  }

  points(): string {
    return this.simulation()?.expected_points.toFixed(1) ?? '—';
  }

  pct(value: number | undefined): string {
    return value === undefined ? '—' : `${(value * 100).toFixed(1)}%`;
  }

  opponent(fixture: Fixture): string {
    return fixture.home_team_id === this.team?.teamId
      ? fixture.away_team
      : fixture.home_team;
  }

  isHomeFixture(fixture: Fixture): boolean {
    return fixture.home_team_id === this.team?.teamId;
  }

  private belongsToTeam(teamName: string): boolean {
    return teamAssetByName(teamName)?.teamId === this.team?.teamId;
  }

  stadiumImage(team: TeamAsset): string {
    return `${team.stadium}?v=20260726-2`;
  }

  useStadiumFallback(event: Event): void {
    const image = event.currentTarget as HTMLImageElement;

    if (!image.dataset['fallbackApplied']) {
      image.dataset['fallbackApplied'] = 'true';
      image.src = 'assets/stadiums/default-stadium.svg';
    }
  }
}
