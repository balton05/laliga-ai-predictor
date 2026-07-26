import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { TEAM_ASSETS } from '../core/team-assets';
import { DataService } from '../data.service';
import { Simulation, Standing } from '../models';
import { TeamLogoComponent } from '../shared/team-logo.component';

interface TeamCard {
  name: string;
  slug: string;
  city: string;
  stadiumName: string;
  standing?: Standing;
  simulation?: Simulation;
}

@Component({
  standalone: true,
  imports: [RouterLink, TeamLogoComponent],
  template: `
    <section class="page">
      <div class="page-heading">
        <div>
          <p class="eyebrow">20 CLUBES · TEMPORADA 2026/27</p>
          <h1>Equipos</h1>
          <p>Explora la proyección, el estadio y los próximos partidos de cada club.</p>
        </div>
        <div class="page-count"><strong>20</strong><span>equipos</span></div>
      </div>

      <div class="teams-grid">
        @for (team of cards(); track team.slug) {
          <a class="team-card card" [routerLink]="['/equipos', team.slug]">
            <div class="team-card__top">
              <app-team-logo [teamName]="team.name" [size]="70" />
              <span class="team-card__position">
                {{ position(team) }}
              </span>
            </div>
            <div class="team-card__identity">
              <h2>{{ team.name }}</h2>
              <span>{{ team.city }} · {{ team.stadiumName }}</span>
            </div>
            <div class="team-card__metrics">
              <div>
                <span>PTS esperados</span>
                <strong>{{ expectedPoints(team) }}</strong>
              </div>
              <div>
                <span>Campeón</span>
                <strong>{{ championProbability(team) }}</strong>
              </div>
            </div>
            <span class="team-card__link">Ver ficha <b>→</b></span>
          </a>
        }
      </div>
    </section>
  `,
})
export class TeamsComponent {
  private readonly data = inject(DataService);
  readonly standings = signal<Standing[]>([]);
  readonly simulation = signal<Simulation[]>([]);
  readonly cards = computed<TeamCard[]>(() => {
    const standings = new Map(
      this.standings().map((row) => [row.team, row] as const),
    );
    const simulations = new Map(
      this.simulation().map((row) => [row.team, row] as const),
    );
    return TEAM_ASSETS.map((team) => ({
      ...team,
      standing: standings.get(team.name),
      simulation: simulations.get(team.name),
    })).sort(
      (a, b) =>
        (a.simulation?.expected_position ?? 99) -
        (b.simulation?.expected_position ?? 99),
    );
  });

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    const [standings, simulation] = await Promise.all([
      this.data.standings(),
      this.data.simulation(),
    ]);
    this.standings.set(standings);
    this.simulation.set(simulation);
  }

  position(team: TeamCard): string {
    const value =
      team.standing?.position ?? team.simulation?.expected_position ?? null;
    return value === null ? '—' : `${value.toFixed(value % 1 ? 1 : 0)}.º`;
  }

  expectedPoints(team: TeamCard): string {
    return team.simulation?.expected_points.toFixed(1) ?? '—';
  }

  championProbability(team: TeamCard): string {
    const value = team.simulation?.champion_probability;
    return value === undefined ? '—' : `${(value * 100).toFixed(1)}%`;
  }
}

