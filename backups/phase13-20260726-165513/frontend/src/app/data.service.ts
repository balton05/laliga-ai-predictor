import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom, timeout } from 'rxjs';

import { Fixture, Health, Prediction, Simulation, Standing } from './models';

type DataMode = 'connecting' | 'api' | 'demo';

@Injectable({ providedIn: 'root' })
export class DataService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl =
    (globalThis as typeof globalThis & { LALIGA_API_URL?: string })
      .LALIGA_API_URL ?? 'http://localhost:8000';

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
}
