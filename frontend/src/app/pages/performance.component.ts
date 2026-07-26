import { Component, computed, inject, signal } from '@angular/core';

import { DataService } from '../data.service';
import {
  CalibrationBin,
  ConfusionCell,
  MatchdayPerformance,
  PerformanceHistory,
  PerformanceSummary,
} from '../models';
import { TeamLogoComponent } from '../shared/team-logo.component';

@Component({
  standalone: true,
  imports: [TeamLogoComponent],
  template: `
    <section class="page performance-page">
      <div class="page-heading">
        <div>
          <p class="eyebrow">EVALUACIÓN FUERA DE MUESTRA</p>
          <h1>Rendimiento real</h1>
          <p>
            Cada resultado se compara con la última predicción válida guardada
            antes del partido. El historial nunca se sobrescribe.
          </p>
        </div>
        <div class="performance-lock">
          <span aria-hidden="true">◇</span>
          <div><strong>Historial inmutable</strong><small>{{ snapshotLabel() }}</small></div>
        </div>
      </div>

      @if (loading()) {
        <div class="performance-kpis">
          @for (item of [1,2,3,4]; track item) {
            <article class="card skeleton-panel"></article>
          }
        </div>
      } @else if (summary(); as metrics) {
        <div class="performance-kpis">
          <article class="card">
            <span>Partidos evaluados</span>
            <strong>{{ metrics.evaluated_matches }}</strong>
            <small>de {{ metrics.completed_matches }} finalizados</small>
          </article>
          <article class="card accent">
            <span>Accuracy 1X2</span>
            <strong>{{ percent(metrics.accuracy) }}</strong>
            <small>{{ metrics.correct_predictions }} pronósticos correctos</small>
          </article>
          <article class="card">
            <span>Log Loss</span>
            <strong>{{ decimal(metrics.log_loss) }}</strong>
            <small>menor es mejor</small>
          </article>
          <article class="card">
            <span>Brier Score</span>
            <strong>{{ decimal(metrics.brier_score) }}</strong>
            <small>error probabilístico 1X2</small>
          </article>
        </div>

        @if (metrics.evaluated_matches === 0) {
          <article class="performance-empty card">
            <div class="empty-orbit"><span>0</span></div>
            <div>
              <p class="eyebrow">SISTEMA PREPARADO</p>
              <h2>Aún no hay partidos para evaluar</h2>
              <p>
                Ya se conservaron {{ metrics.fixtures_with_snapshot }}
                pronósticos prepartido. Cuando Football-Data publique el
                primer resultado, las métricas aparecerán automáticamente.
              </p>
              <div class="empty-checks">
                <span>✓ Predicciones congeladas</span>
                <span>✓ Modelo versionado</span>
                <span>✓ Evaluación automática</span>
              </div>
            </div>
          </article>
        } @else {
          <div class="performance-grid">
            <article class="card matchday-chart">
              <div class="card-heading">
                <span>Rendimiento por jornada</span>
                <small>Accuracy acumulada por bloque</small>
              </div>
              <div class="matchday-bars">
                @for (day of matchdays(); track day.matchday) {
                  <div class="matchday-bar-row">
                    <span>J{{ day.matchday }}</span>
                    <div class="bar-track">
                      <div [style.width.%]="day.accuracy * 100"></div>
                    </div>
                    <strong>{{ percent(day.accuracy) }}</strong>
                    <small>{{ day.correct }}/{{ day.matches }}</small>
                  </div>
                }
              </div>
            </article>

            <article class="card market-card">
              <div class="card-heading">
                <span>Modelo frente al mercado</span>
                <small>{{ metrics.market_matches }} comparaciones</small>
              </div>
              <div class="market-comparison">
                <div>
                  <span>LaLiga AI</span>
                  <strong>{{ decimal(metrics.log_loss) }}</strong>
                  <small>Log Loss</small>
                </div>
                <div class="versus-dot">VS</div>
                <div>
                  <span>Cuotas</span>
                  <strong>{{ decimal(metrics.market_log_loss) }}</strong>
                  <small>Log Loss sin margen</small>
                </div>
              </div>
              <p>{{ marketMessage() }}</p>
            </article>
          </div>

          <div class="performance-grid lower">
            <article class="card confusion-card">
              <div class="card-heading">
                <span>Matriz de confusión</span>
                <small>Real × Pronosticado</small>
              </div>
              <div class="confusion-matrix">
                <span></span><b>1</b><b>X</b><b>2</b>
                @for (actual of outcomes; track actual) {
                  <b>{{ outcomeLabel(actual) }}</b>
                  @for (predicted of outcomes; track predicted) {
                    <span [class.correct-cell]="actual === predicted">
                      {{ confusionValue(actual, predicted) }}
                    </span>
                  }
                }
              </div>
            </article>

            <article class="card calibration-card">
              <div class="card-heading">
                <span>Calibración</span>
                <small>Confianza vs. frecuencia observada</small>
              </div>
              <div class="calibration-list">
                @for (bin of activeCalibration(); track bin.label) {
                  <div>
                    <span>{{ bin.label }}</span>
                    <div class="calibration-track">
                      <i [style.width.%]="(bin.mean_confidence ?? 0) * 100"></i>
                      <b [style.left.%]="(bin.observed_accuracy ?? 0) * 100"></b>
                    </div>
                    <small>{{ bin.matches }} partidos</small>
                  </div>
                }
              </div>
              <div class="calibration-legend">
                <span><i></i> Confianza</span>
                <span><b></b> Accuracy real</span>
              </div>
            </article>
          </div>

          <article class="card performance-history">
            <div class="card-heading">
              <span>Historial evaluado</span>
              <small>Predicción registrada antes del resultado</small>
            </div>
            <div class="history-table">
              <div class="history-head">
                <span>Partido</span><span>Pronóstico</span><span>Resultado</span>
                <span>Log Loss</span><span>Estado</span>
              </div>
              @for (match of history(); track match.fixture_id) {
                <div class="history-row">
                  <div class="history-match">
                    <app-team-logo [teamName]="match.home_team" [size]="28" />
                    <span>{{ match.home_team }} – {{ match.away_team }}<small>J{{ match.matchday }}</small></span>
                    <app-team-logo [teamName]="match.away_team" [size]="28" />
                  </div>
                  <strong>{{ outcomeLabel(match.predicted_ftr) }}</strong>
                  <strong>{{ match.home_goals }}–{{ match.away_goals }}</strong>
                  <span>{{ match.log_loss.toFixed(3) }}</span>
                  <b [class.hit]="match.correct">{{ match.correct ? 'Acierto' : 'Fallo' }}</b>
                </div>
              }
            </div>
          </article>
        }
      }
    </section>
  `,
})
export class PerformanceComponent {
  private readonly data = inject(DataService);
  readonly loading = signal(true);
  readonly summary = signal<PerformanceSummary | null>(null);
  readonly history = signal<PerformanceHistory[]>([]);
  readonly matchdays = signal<MatchdayPerformance[]>([]);
  readonly confusion = signal<ConfusionCell[]>([]);
  readonly calibration = signal<CalibrationBin[]>([]);
  readonly outcomes: Array<'H' | 'D' | 'A'> = ['H', 'D', 'A'];
  readonly activeCalibration = computed(() =>
    this.calibration().filter((bin) => bin.matches > 0),
  );

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    const [summary, history, matchdays, confusion, calibration] =
      await Promise.all([
        this.data.performanceSummary(),
        this.data.performanceHistory(),
        this.data.performanceByMatchday(),
        this.data.performanceConfusion(),
        this.data.performanceCalibration(),
      ]);
    this.summary.set(summary);
    this.history.set(history);
    this.matchdays.set(matchdays);
    this.confusion.set(confusion);
    this.calibration.set(calibration);
    this.loading.set(false);
  }

  snapshotLabel(): string {
    const value = this.summary()?.prediction_snapshots ?? 0;
    return `${value} versiones conservadas`;
  }

  percent(value: number | null): string {
    return value === null ? '—' : `${(value * 100).toFixed(1)}%`;
  }

  decimal(value: number | null): string {
    return value === null ? '—' : value.toFixed(3);
  }

  outcomeLabel(value: 'H' | 'D' | 'A'): string {
    return { H: '1', D: 'X', A: '2' }[value];
  }

  confusionValue(
    actual: 'H' | 'D' | 'A',
    predicted: 'H' | 'D' | 'A',
  ): number {
    return (
      this.confusion().find(
        (cell) =>
          cell.actual_ftr === actual && cell.predicted_ftr === predicted,
      )?.matches ?? 0
    );
  }

  marketMessage(): string {
    const metrics = this.summary();
    if (!metrics || metrics.market_matches === 0) {
      return 'La comparación se activará cuando existan cuotas y resultados.';
    }
    if (
      metrics.log_loss !== null &&
      metrics.market_log_loss !== null &&
      metrics.log_loss < metrics.market_log_loss
    ) {
      return 'El modelo registra menor error probabilístico que el mercado en la muestra disponible.';
    }
    return 'El mercado registra menor error en la muestra disponible; seguiremos midiendo jornada a jornada.';
  }
}
