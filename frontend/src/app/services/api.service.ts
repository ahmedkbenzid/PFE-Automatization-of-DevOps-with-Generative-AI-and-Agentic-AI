import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { Artifacts, RunRequest } from '../models/run.model';

interface StartRunResponse {
  run_id: string;
}

export interface RunStatusResponse {
  run_id: string;
  running: boolean;
  returncode: number | null;
  line_count: number;
}

export interface RunLogsResponse {
  run_id: string;
  lines: string[];
  offset: number;
  limit: number;
  total: number;
  has_more: boolean;
}

export interface ExecutionLogEntry {
  stream?: string;
  line?: string;
  level?: 'info' | 'warn' | 'error';
  stage?: string;
  [key: string]: unknown;
}

export interface ExecutionLogsResponse {
  run_id: string;
  logs: ExecutionLogEntry[];
  count: number;
}

export interface ExecutionResultResponse {
  run_id?: string;
  status?: 'pending' | 'running' | 'completed' | 'error' | string;
  started?: boolean;
  message?: string;
  act?: {
    exit_code?: number;
    logs?: ExecutionLogEntry[];
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface ExecutionPlanResponse {
  run_id: string;
  plan: {
    execution_order?: Array<string | string[]>;
    tasks?: Array<any>;
    estimated_time_sec?: number;
    [key: string]: unknown;
  };
  complexity_score: number;
  planner_reasoning: string;
  status: string;
  plan_only: boolean;
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

  getLogs(runId: string, offset: number = 0, limit: number = 100): Observable<RunLogsResponse> {
    return this.http.get<RunLogsResponse>(
      `${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/logs`,
      { params: { offset, limit } },
    );
  }

  /**
   * Get post-run execution result produced by the execution agent (if any)
   */
  getExecution(runId: string): Observable<ExecutionResultResponse> {
    return this.http.get<ExecutionResultResponse>(`${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/execution`);
  }
  startExecutionForRun(
    runId: string,
    payload: { force?: boolean; artifacts?: Record<string, unknown> } = {},
  ): Observable<ExecutionResultResponse> {
    return this.http.post<ExecutionResultResponse>(
      `${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/execution/start`,
      payload,
    );
  }

  saveEditedArtifacts(runId: string, artifacts: Record<string, unknown>): Observable<{ ok: boolean; run_id: string }> {
    return this.http.post<{ ok: boolean; run_id: string }>(
      `${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/artifacts/edited`,
      { artifacts },
    );
  }
  getExecutionPlan(runId: string): Observable<ExecutionPlanResponse> {
    return this.http.get<ExecutionPlanResponse>(`${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/plan`);
  }

  /**
   * Get execution logs streamed from the execution agent
   */
  getExecutionLogs(runId: string): Observable<ExecutionLogsResponse> {
    return this.http.get<ExecutionLogsResponse>(`${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/execution/logs`);
  }

  /**
   * Request a stop/repair action for a run (used to stop execution or cleanup)
   */
  repairRun(runId: string, payload: Record<string, any> = {}): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/repair`, payload);
  }

  /**
   * Request the LLM-as-a-Judge to analyse the orchestrator logs of a run.
   * Returns a structured verdict with status, root-cause, per-agent breakdown, etc.
   */
  judgeRun(runId: string, force: boolean = false): Observable<JudgeVerdictResponse> {
    const params = force ? new HttpParams().set('force', 'true') : undefined;
    return this.http.post<JudgeVerdictResponse>(
      `${this.baseUrl}/api/judge/${encodeURIComponent(runId)}`,
      null,
      { params },
    );
  }
}

// ─── LLM Judge types ────────────────────────────────────────────────────────

export interface AgentVerdictResponse {
  agent_name: string;
  status: string;          // "success" | "failed" | "skipped"
  summary: string;
  errors: string[];
  warnings: string[];
}

export interface JudgeVerdictResponse {
  run_id: string | null;
  overall_status: string;  // "success" | "partial_success" | "failed" | "error"
  confidence: number;
  summary: string;
  root_cause: string | null;
  agents: AgentVerdictResponse[];
  errors_found: string[];
  warnings_found: string[];
  recommendations: string[];
  token_usage: Record<string, number>;
  cleaned_log_length: number;
  cached: boolean;
}
