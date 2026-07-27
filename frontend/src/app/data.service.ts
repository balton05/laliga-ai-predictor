import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom, timeout } from 'rxjs';

import {
  AutomationStatus,
  CalibrationBin,
  ConfusionCell,
  Fixture,
  Health,
  MatchdayPerformance,
  ModelStatus,
  ModelTrainingRun,
  ModelVersion,
  PerformanceHistory,
  PerformanceSummary,
  Prediction,
  Simulation,
  Standing,
} from './models';

type DataMode = 'connecting' | 'api' | 'demo';

@Injectable({ providedIn: 'root' })
export class DataService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl =
    (globalThis as typeof globalThis & { LALIGA_API_URL?: string })
      .LALIGA_API_URL ?? '/api';

  readonly mode = signal<DataMode>('connecting');
  readonly modeLabel = computed(() => {
    if (this.mode() === 'api') return 'API en línea';
    if (this.mode() === 'demo') return 'Datos de pretemporada';
    return 'Conectando';
  });

  private async request<T>(endpoint: string, fallback: string): Promise<T> {
    try {
      const response = await firstValueFrom(
        this.http.get<T>(`${this.apiUrl}${endpoint}`).pipe(timeout(2200)),
      );
      this.mode.set('api');
      return response;
    } catch {
      const response = await firstValueFrom(
        this.http.get<T>(`assets/demo/${fallback}`),
      );
      this.mode.set('demo');
      return response;
    }
  }

  health(): Promise<Health> {
    return this.request<Health>('/health', 'health.json');
  }

  fixtures(): Promise<Fixture[]> {
    return this.request<Fixture[]>('/fixtures', 'fixtures.json');
  }

  predictions(): Promise<Prediction[]> {
    return this.request<Prediction[]>('/predictions', 'predictions.json');
  }

  standings(): Promise<Standing[]> {
    return this.request<Standing[]>('/standings', 'standings.json');
  }

  simulation(): Promise<Simulation[]> {
    return this.request<Simulation[]>('/simulation', 'simulation.json');
  }

  automationStatus(): Promise<AutomationStatus> {
    return this.request<AutomationStatus>(
      '/automation/status',
      'automation.json',
    );
  }

  performanceSummary(): Promise<PerformanceSummary> {
    return this.request<PerformanceSummary>(
      '/performance/summary',
      'performance-summary.json',
    );
  }

  performanceHistory(): Promise<PerformanceHistory[]> {
    return this.request<PerformanceHistory[]>(
      '/performance/history?limit=100',
      'performance-history.json',
    );
  }

  performanceByMatchday(): Promise<MatchdayPerformance[]> {
    return this.request<MatchdayPerformance[]>(
      '/performance/by-matchday',
      'performance-by-matchday.json',
    );
  }

  performanceConfusion(): Promise<ConfusionCell[]> {
    return this.request<ConfusionCell[]>(
      '/performance/confusion',
      'performance-confusion.json',
    );
  }

  performanceCalibration(): Promise<CalibrationBin[]> {
    return this.request<CalibrationBin[]>(
      '/performance/calibration',
      'performance-calibration.json',
    );
  }

  modelStatus(): Promise<ModelStatus> {
    return this.request<ModelStatus>('/models/status', 'models-status.json');
  }

  modelVersions(): Promise<ModelVersion[]> {
    return this.request<ModelVersion[]>('/models', 'models-versions.json');
  }

  modelTrainingRuns(): Promise<ModelTrainingRun[]> {
    return this.request<ModelTrainingRun[]>(
      '/models/training-runs?limit=10',
      'models-training-runs.json',
    );
  }
}
