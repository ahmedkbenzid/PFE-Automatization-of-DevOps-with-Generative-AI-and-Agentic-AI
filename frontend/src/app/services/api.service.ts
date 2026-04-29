import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { Artifacts, RunRequest } from '../models/run.model';

interface StartRunResponse {
  run_id: string;
}

interface RunStatusResponse {
  run_id: string;
  running: boolean;
  returncode: number | null;
  line_count: number;
}

@Injectable({
  providedIn: 'root',
})
export class ApiService {
  private readonly baseUrl = environment.apiUrl;

  constructor(private readonly http: HttpClient) {}

  startRun(request: RunRequest): Observable<StartRunResponse> {
    return this.http.post<StartRunResponse>(`${this.baseUrl}/api/runs`, request);
  }

  getArtifacts(runId: string): Observable<Artifacts> {
    return this.http.get<Artifacts>(`${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/artifacts`);
  }

  approveRun(runId: string, approved: boolean, editedPlan: Array<string | string[]>): Observable<{ ok: boolean; file: string }> {
    return this.http.post<{ ok: boolean; file: string }>(
      `${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/approve`,
      {
        approved,
        edited_execution_order: editedPlan,
      },
    );
  }

  getStatus(runId: string): Observable<RunStatusResponse> {
    return this.http.get<RunStatusResponse>(`${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/status`);
  }
}
