import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DataService } from '../data.service';
import { Simulation } from '../models';

type Zone = 'title' | 'top4' | 'europe' | 'relegation';

@Component({
  standalone: true,
  imports: [FormsModule],
  template: `
    <section class="page">
      <div class="page-heading">
        <div>
          <p class="eyebrow">50,000 TEMPORADAS MONTE CARLO</p>
          <h1>Simulación de temporada</h1>
          <p>La distribución completa de campeón, Europa, descenso, puntos y posición probable.</p>
        </div>
        <div class="simulation-seed"><span>Semilla</span><strong>42</strong></div>
      </div>

      <div class="zone-tabs" role="tablist" aria-label="Zona de clasificación">
        <button [class.active]="zone() === 'title'" (click)="zone.set('title')">Campeón</button>
        <button [class.active]="zone() === 'top4'" (click)="zone.set('top4')">Top 4</button>
        <button [class.active]="zone() === 'europe'" (click)="zone.set('europe')">Top 7</button>
        <button [class.active]="zone() === 'relegation'" (click)="zone.set('relegation')">Descenso</button>
      </div>

      <div class="simulation-layout">
        <article class="probability-ranking card">
          <div class="card-heading">
            <span>{{ zoneTitle() }}</span>
            <span>Probabilidad</span>
          </div>
          <div class="ranking-bars">
            @for (team of ranked().slice(0, 10); track team.team_id; let index = $index) {
              <div class="ranking-row">
                <span class="rank">{{ index + 1 }}</span>
                <span class="mini-crest">{{ initials(team.team) }}</span>
                <strong>{{ team.team }}</strong>
                <div class="bar-track">
                  <div
                    [class.relegation-bar]="zone() === 'relegation'"
                    [style.width.%]="barWidth(value(team))"
                  ></div>
                </div>
                <b>{{ pct(value(team)) }}</b>
              </div>
            }
          </div>
        </article>

        @if (selected(); as team) {
          <aside class="team-projection card">
            <div class="projection-team">
              <span class="crest">{{ initials(team.team) }}</span>
              <div><small>Proyección destacada</small><h2>{{ team.team }}</h2></div>
            </div>
            <div class="projection-position">
              <strong>{{ team.expected_position.toFixed(1) }}</strong>
              <span>posición media</span>
            </div>
            <div class="projection-points">
              <div><span>Puntos esperados</span><strong>{{ team.expected_points.toFixed(1) }}</strong></div>
              <div><span>Intervalo P05–P95</span><strong>{{ team.points_p05.toFixed(0) }}–{{ team.points_p95.toFixed(0) }}</strong></div>
            </div>
            <div class="projection-zones">
              <div><span>Campeón</span><b>{{ pct(team.champion_probability) }}</b></div>
              <div><span>Top 4</span><b>{{ pct(team.top4_probability) }}</b></div>
              <div><span>Top 7</span><b>{{ pct(team.europe_top7_probability) }}</b></div>
              <div><span>Descenso</span><b class="danger">{{ pct(team.relegation_probability) }}</b></div>
            </div>
            <p>
              El intervalo expresa incertidumbre entre temporadas simuladas; no
              es un margen de error del modelo.
            </p>
          </aside>
        }
      </div>

      <article class="method-card card">
        <span class="method-number">50K</span>
        <div><strong>Temporadas completas</strong><small>Cada partido se sortea con probabilidades calibradas.</small></div>
        <span class="method-arrow">→</span>
        <span class="method-number">380</span>
        <div><strong>Partidos por simulación</strong><small>Marcadores Poisson condicionados al resultado 1X2.</small></div>
        <span class="method-arrow">→</span>
        <span class="method-number">20</span>
        <div><strong>Distribuciones finales</strong><small>Tabla con mini-liga para desempates.</small></div>
      </article>
    </section>
  `,
})
export class SimulationComponent {
  private readonly data = inject(DataService);
  readonly simulation = signal<Simulation[]>([]);
  readonly zone = signal<Zone>('title');
  readonly ranked = computed(() =>
    [...this.simulation()].sort((a, b) => this.value(b) - this.value(a)),
  );
  readonly selected = computed(() => this.ranked()[0]);

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.simulation.set(await this.data.simulation());
  }

  value(team: Simulation): number {
    const key = {
      title: team.champion_probability,
      top4: team.top4_probability,
      europe: team.europe_top7_probability,
      relegation: team.relegation_probability,
    };
    return key[this.zone()];
  }

  zoneTitle(): string {
    return {
      title: 'Probabilidad de campeón',
      top4: 'Probabilidad de Top 4',
      europe: 'Probabilidad de Top 7',
      relegation: 'Probabilidad de descenso',
    }[this.zone()];
  }

  pct(value: number): string {
    return `${(value * 100).toFixed(1)}%`;
  }

  barWidth(value: number): number {
    const maximum = this.ranked().length ? this.value(this.ranked()[0]) : 1;
    return maximum > 0 ? (value / maximum) * 100 : 0;
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
