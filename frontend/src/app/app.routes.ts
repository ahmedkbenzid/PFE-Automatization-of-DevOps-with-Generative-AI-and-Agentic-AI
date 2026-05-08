import { Routes } from '@angular/router';

import { CicdRunPageComponent } from './components/cicd-run-page/cicd-run-page.component';
import { RunDashboardComponent } from './components/run-dashboard/run-dashboard.component';
import { RunFormComponent } from './components/run-form/run-form.component';
import { HistoryDashboardComponent } from './components/history-dashboard/history-dashboard.component';

export const routes: Routes = [
  { path: '', component: RunFormComponent },
  { path: 'runs/:id', component: RunDashboardComponent },
  { path: 'cicd/:id', component: CicdRunPageComponent },
  {path: 'history', component: HistoryDashboardComponent,title: 'Session History'},
];
