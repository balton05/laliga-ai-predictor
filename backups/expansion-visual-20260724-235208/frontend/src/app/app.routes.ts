import { Routes } from '@angular/router';

import { CalendarComponent } from './pages/calendar.component';
import { HomeComponent } from './pages/home.component';
import { PredictionsComponent } from './pages/predictions.component';
import { SimulationComponent } from './pages/simulation.component';
import { StandingsComponent } from './pages/standings.component';

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
  { path: '**', redirectTo: '' },
];
