import { Component, computed, inject, signal } from '@angular/core';

import { DataService } from '../data.service';
import { Simulation, Standing } from '../models';

type TableRow = Standing & {
  expectedPosition: number;
  expectedPoints: number;
};

@Component({
  standalone: true,
  template: `
    <section class="page">
      <div class="page-heading">
        <div>
          <p class="eyebrow">TABLA ACTUAL Y PROYECCIÓN</p>
          <h1>Clasificación</h1>
          <p>En pretemporada, el orden se basa en la posición media de 50,000 simulaciones.</p>
        </div>
        <div class="projection-badge">Vista proyectada</div>
      </div>

      <article class="table-card card">
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Pos.</th>
                <th>Equipo</th>
                <th class="numeric">PJ</th>
                <th class="numeric">PTS</th>
                <th class="numeric">PTS esp.</th>
                <th class="numeric">Pos. media</th>
                <th>Zona</th>
              </tr>
            </thead>
            <tbody>
              @for (row of rows(); track row.team_id; let index = $index) {
                <tr>
                  <td>
                    <span class="position-number" [class]="zoneClass(index + 1)">
                      {{ index + 1 }}
                    </span>
                  </td>
                  <td class="team-cell">
                    <span class="mini-crest">{{ initials(row.team) }}</span>
                    <strong>{{ row.team }}</strong>
                  </td>
                  <td class="numeric">{{ row.played }}</td>
                  <td class="numeric"><strong>{{ row.points }}</strong></td>
                  <td class="numeric">{{ row.expectedPoints.toFixed(1) }}</td>
                  <td class="numeric">{{ row.expectedPosition.toFixed(1) }}</td>
                  <td><span class="zone-chip" [class]="zoneClass(index + 1)">{{ zone(index + 1) }}</span></td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        <div class="table-legend">
          <span><i class="champions"></i> Champions</span>
          <span><i class="europe"></i> Europa</span>
          <span><i class="relegation"></i> Descenso</span>
        </div>
      </article>
    </section>
  `,
})
export class StandingsComponent {
  private readonly data = inject(DataService);
  readonly standings = signal<Standing[]>([]);
  readonly simulation = signal<Simulation[]>([]);
  readonly rows = computed<TableRow[]>(() => {
    const simulations = new Map(
      this.simulation().map((row) => [row.team_id, row]),
    );
    return this.standings()
      .map((row) => ({
        ...row,
        expectedPosition:
          simulations.get(row.team_id)?.expected_position ?? 20,
        expectedPoints: simulations.get(row.team_id)?.expected_points ?? 0,
      }))
      .sort((a, b) => {
        if (a.played || b.played) {
          return (
            b.points - a.points ||
            b.goal_difference - a.goal_difference ||
            a.expectedPosition - b.expectedPosition
          );
        }
        return a.expectedPosition - b.expectedPosition;
      });
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

  zone(position: number): string {
    if (position <= 4) return 'Champions';
    if (position <= 7) return 'Europa';
    if (position >= 18) return 'Descenso';
    return 'LaLiga';
  }

  zoneClass(position: number): string {
    if (position <= 4) return 'champions';
    if (position <= 7) return 'europe';
    if (position >= 18) return 'relegation';
    return 'neutral-zone';
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
