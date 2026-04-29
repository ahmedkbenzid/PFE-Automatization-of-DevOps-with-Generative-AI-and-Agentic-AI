import { Routes } from '@angular/router';

import { RunDashboardComponent } from './components/run-dashboard/run-dashboard.component';
import { RunFormComponent } from './components/run-form/run-form.component';

export const routes: Routes = [
  { path: '', component: RunFormComponent },
  { path: 'runs/:id', component: RunDashboardComponent },
];
