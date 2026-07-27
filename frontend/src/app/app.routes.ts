import { Routes } from '@angular/router';

import { CalendarComponent } from './pages/calendar.component';
import { HomeComponent } from './pages/home.component';
import { ModelsComponent } from './pages/models.component';
import { PerformanceComponent } from './pages/performance.component';
import { PredictionsComponent } from './pages/predictions.component';
import { SimulationComponent } from './pages/simulation.component';
import { StandingsComponent } from './pages/standings.component';
import { TeamDetailComponent } from './pages/team-detail.component';
import { TeamsComponent } from './pages/teams.component';

export const routes: Routes = [
  { path: '', component: HomeComponent, title: 'Resumen · LaLiga AI' },
  {
    path: 'pronosticos',
    component: PredictionsComponent,
    title: 'Pronósticos · LaLiga AI',
  },
  {
    path: 'calendario',
    component: CalendarComponent,
    title: 'Calendario · LaLiga AI',
  },
  {
    path: 'clasificacion',
    component: StandingsComponent,
    title: 'Clasificación · LaLiga AI',
  },
  {
    path: 'simulacion',
    component: SimulationComponent,
    title: 'Simulación · LaLiga AI',
  },
  {
    path: 'rendimiento',
    component: PerformanceComponent,
    title: 'Rendimiento · LaLiga AI',
  },
  {
    path: 'modelos',
    component: ModelsComponent,
    title: 'Modelos · LaLiga AI',
  },
  {
    path: 'equipos',
    component: TeamsComponent,
    title: 'Equipos · LaLiga AI',
  },
  {
    path: 'equipos/:slug',
    component: TeamDetailComponent,
    title: 'Ficha de equipo · LaLiga AI',
  },
  { path: '**', redirectTo: '' },
];
