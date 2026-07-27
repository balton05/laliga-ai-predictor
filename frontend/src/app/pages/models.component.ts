import { Component, computed, inject, signal } from '@angular/core';

import { DataService } from '../data.service';
import { ModelStatus, ModelTrainingRun, ModelVersion } from '../models';

@Component({
  standalone: true,
  template: `
    <section class="page models-page">
      <div class="page-heading">
        <div>
          <p class="eyebrow">GOBIERNO DEL MODELO</p>
          <h1>Versiones y reentrenamiento</h1>
          <p>
            El campeón permanece congelado mientras cada challenger se entrena
            y evalúa en un bloque temporal independiente.
          </p>
        </div>
        <div class="model-governance-badge">
          <span>✓</span>
          <div>
            <strong>Promoción controlada</strong>
            <small>Ningún modelo se activa automáticamente</small>
          </div>
        </div>
      </div>

      @if (loading()) {
        <div class="model-kpis">
          @for (item of [1,2,3,4]; track item) {
            <article class="card skeleton-panel"></article>
          }
        </div>
      } @else if (status(); as state) {
        <div class="model-kpis">
          <article class="card model-kpi-wide">
            <span>Modelo activo</span>
            <strong>{{ compactVersion(state.active_model) }}</strong>
            <small>Entrenado hasta {{ state.active_trained_through }}</small>
          </article>
          <article class="card">
            <span>Partidos evaluados</span>
            <strong>{{ state.evaluated_matches }}</strong>
            <small>mínimo {{ state.minimum_matches }}</small>
          </article>
          <article class="card">
            <span>Jornadas observadas</span>
            <strong>{{ state.completed_matchdays }}</strong>
            <small>mínimo {{ state.minimum_matchdays }}</small>
          </article>
          <article class="card" [class.accent]="state.ready_to_retrain">
            <span>Próximo entrenamiento</span>
            <strong>{{ state.ready_to_retrain ? 'Disponible' : 'En espera' }}</strong>
            <small>{{ readinessLabel() }}</small>
          </article>
        </div>

        <article class="card retraining-policy">
          <div class="policy-copy">
            <p class="eyebrow">POLÍTICA DE REENTRENAMIENTO</p>
            <h2>{{ state.ready_to_retrain ? 'La muestra ya es suficiente' : 'Esperando evidencia real' }}</h2>
            <p>
              Las predicciones se dividen cronológicamente: 70% para ajustar
              el challenger y 30% para compararlo fuera de muestra. Solo puede
              promocionarse si mejora el Log Loss sin deteriorar el Brier Score.
            </p>
          </div>
          <div class="readiness-meter">
            <div>
              <span>Partidos</span>
              <strong>{{ state.evaluated_matches }}/{{ state.minimum_matches }}</strong>
            </div>
            <div class="meter-track">
              <i [style.width.%]="matchProgress()"></i>
            </div>
            <div>
              <span>Jornadas</span>
              <strong>{{ state.completed_matchdays }}/{{ state.minimum_matchdays }}</strong>
            </div>
            <div class="meter-track secondary">
              <i [style.width.%]="matchdayProgress()"></i>
            </div>
          </div>
        </article>

        <div class="models-layout">
          <article class="card registry-card">
            <div class="card-heading">
              <span>Registro de modelos</span>
              <small>{{ versions().length }} versiones conservadas</small>
            </div>
            <div class="model-version-list">
              @for (model of versions(); track model.version) {
                <div class="model-version-row">
                  <div class="version-state" [class]="model.stage">
                    {{ stageLabel(model.stage) }}
                  </div>
                  <div class="version-main">
                    <strong>{{ compactVersion(model.version) }}</strong>
                    <small>{{ familyLabel(model.family) }} · {{ model.trained_through }}</small>
                  </div>
                  <div class="version-metric">
                    <span>Log Loss</span>
                    <strong>{{ decimal(model.validation_log_loss) }}</strong>
                  </div>
                  <div class="version-metric">
                    <span>Brier</span>
                    <strong>{{ decimal(model.validation_brier_score) }}</strong>
                  </div>
                  <div class="version-metric">
                    <span>Accuracy</span>
                    <strong>{{ percent(model.validation_accuracy) }}</strong>
                  </div>
                </div>
              }
            </div>
          </article>

          <article class="card training-card">
            <div class="card-heading">
              <span>Última ejecución</span>
              <small>Auditoría del entrenamiento</small>
            </div>
            @if (latestRun(); as run) {
              <div class="training-status" [class]="run.status">
                <span></span>
                {{ runStatusLabel(run.status) }}
              </div>
              <dl>
                <div><dt>Disparador</dt><dd>{{ run.trigger === 'manual' ? 'Manual' : 'Programado' }}</dd></div>
                <div><dt>Muestra</dt><dd>{{ run.evaluated_matches }} partidos</dd></div>
                <div><dt>Entrenamiento</dt><dd>{{ run.train_matches || '—' }}</dd></div>
                <div><dt>Validación</dt><dd>{{ run.validation_matches || '—' }}</dd></div>
                <div><dt>Mejora Log Loss</dt><dd>{{ signed(run.log_loss_improvement) }}</dd></div>
              </dl>
              <p>{{ run.error_message || runMessage(run) }}</p>
            } @else {
              <div class="training-empty">
                <strong>Sin ejecuciones todavía</strong>
                <p>El registro comenzará cuando se solicite el primer reentrenamiento.</p>
              </div>
            }
          </article>
        </div>
      }
    </section>
  `,
})
export class ModelsComponent {
  private readonly data = inject(DataService);
  readonly loading = signal(true);
  readonly status = signal<ModelStatus | null>(null);
  readonly versions = signal<ModelVersion[]>([]);
  readonly runs = signal<ModelTrainingRun[]>([]);
  readonly latestRun = computed(() => this.runs()[0] ?? null);

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    const [status, versions, runs] = await Promise.all([
      this.data.modelStatus(),
      this.data.modelVersions(),
      this.data.modelTrainingRuns(),
    ]);
    this.status.set(status);
    this.versions.set(versions);
    this.runs.set(runs);
    this.loading.set(false);
  }

  matchProgress(): number {
    const state = this.status();
    return state
      ? Math.min(100, (state.evaluated_matches / state.minimum_matches) * 100)
      : 0;
  }

  matchdayProgress(): number {
    const state = this.status();
    return state
      ? Math.min(100, (state.completed_matchdays / state.minimum_matchdays) * 100)
      : 0;
  }

  readinessLabel(): string {
    const state = this.status();
    if (!state) return '';
    if (state.ready_to_retrain) return 'validación temporal habilitada';
    const matches = Math.max(0, state.minimum_matches - state.evaluated_matches);
    const days = Math.max(0, state.minimum_matchdays - state.completed_matchdays);
    return `faltan ${matches} partidos y ${days} jornadas`;
  }

  compactVersion(version: string): string {
    return version.replace('ensemble-', 'Ensemble ').replaceAll('-', ' ');
  }

  decimal(value: number | null): string {
    return value === null ? '—' : value.toFixed(3);
  }

  percent(value: number | null): string {
    return value === null ? '—' : `${(value * 100).toFixed(1)}%`;
  }

  signed(value: number | null): string {
    if (value === null) return '—';
    return `${value >= 0 ? '+' : ''}${value.toFixed(4)}`;
  }

  stageLabel(stage: ModelVersion['stage']): string {
    return {
      active: 'Activo',
      candidate: 'Candidato',
      rejected: 'Descartado',
      archived: 'Archivado',
    }[stage];
  }

  familyLabel(family: string): string {
    return family === 'calibrated_ensemble'
      ? 'Ensemble recalibrado'
      : 'Ensemble deportivo';
  }

  runStatusLabel(status: ModelTrainingRun['status']): string {
    return {
      running: 'En ejecución',
      not_ready: 'Muestra insuficiente',
      candidate_ready: 'Candidato aprobado',
      rejected: 'Candidato descartado',
      failed: 'Ejecución fallida',
    }[status];
  }

  runMessage(run: ModelTrainingRun): string {
    return run.eligible_for_promotion
      ? 'El challenger superó las puertas estadísticas y puede revisarse para promoción.'
      : 'El campeón permanece activo; ningún cambio se aplicó a producción.';
  }
}
