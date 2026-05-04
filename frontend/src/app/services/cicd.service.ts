import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, Subject } from 'rxjs';
import { webSocket } from 'rxjs/webSocket';
import { environment } from '../../environments/environment';

export interface PipelineConfig {
  stages: string[];
  [key: string]: any;
}

export interface BuildRequest {
  pipeline_config: PipelineConfig;
  secrets: Record<string, string>;
  work_dir?: string;
}

export interface BuildStatusResponse {
  execution_id: string;
  started_at: number;
  completed_at: number | null;
  returncode: number | null;
  total_lines: number;
  stages: Record<string, StageStatus>;
}

export interface StageStatus {
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  start_time: number | null;
  end_time: number | null;
  duration: number | null;
  log_count: number;
  error: string | null;
}

export interface BuildLogEvent {
  type: 'log' | 'complete' | 'error';
  execution_id: string;
  line?: string;
  level?: 'info' | 'warn' | 'error';
  stage?: string;
  stage_status?: 'running' | 'completed' | 'failed';
  line_index?: number;
  returncode?: number;
  stages?: Record<string, StageStatus>;
  total_lines?: number;
  message?: string;
}

@Injectable({
  providedIn: 'root',
})
export class CicdService {
  private readonly baseUrl = environment.apiUrl;

  constructor(private readonly http: HttpClient) {}

  /**
   * Ensure execution-sandbox is started for a run id.
   * Safe to call multiple times; backend returns already_started if running.
   */
  startExecutionForRun(runId: string): Observable<any> {
    return this.http.post<any>(
      `${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/execution/start`,
      {}
    );
  }

  /**
   * Start a CI/CD build execution in Docker sandbox
   */
  startBuild(request: BuildRequest): Observable<{ execution_id: string }> {
    return this.http.post<{ execution_id: string }>(
      `${this.baseUrl}/api/cicd/build`,
      request
    );
  }

  /**
   * Get current status of a build execution
   */
  getBuildStatus(executionId: string): Observable<BuildStatusResponse> {
    return this.http.get<BuildStatusResponse>(
      `${this.baseUrl}/api/cicd/build/${encodeURIComponent(executionId)}/status`
    );
  }

  /**
   * Get build logs
   */
  getBuildLogs(
    executionId: string,
    startLine: number = 0,
    limit: number = 100
  ): Observable<{ logs: string[]; total_available: number }> {
    return this.http.get<{ logs: string[]; total_available: number }>(
      `${this.baseUrl}/api/cicd/build/${encodeURIComponent(executionId)}/logs`,
      { params: { start_line: startLine, limit } }
    );
  }

  /**
   * Stream build logs via WebSocket
   */
  streamBuildLogs(executionId: string): Observable<BuildLogEvent> {
    const wsUrl = `${environment.apiUrl.replace('http', 'ws')}/api/cicd/build/${encodeURIComponent(
      executionId
    )}/ws`;
    return webSocket(wsUrl);
  }

  /**
   * Stop a running build
   */
  stopBuild(executionId: string): Observable<{ stopped: boolean }> {
    return this.http.post<{ stopped: boolean }>(
      `${this.baseUrl}/api/cicd/build/${encodeURIComponent(executionId)}/stop`,
      {}
    );
  }

  /**
   * Get build artifacts after completion
   */
  getBuildArtifacts(executionId: string): Observable<any> {
    return this.http.get(
      `${this.baseUrl}/api/cicd/build/${encodeURIComponent(executionId)}/artifacts`
    );
  }

  /**
   * Clean up a build execution
   */
  cleanupBuild(executionId: string): Observable<{ cleaned_up: boolean }> {
    return this.http.post<{ cleaned_up: boolean }>(
      `${this.baseUrl}/api/cicd/build/${encodeURIComponent(executionId)}/cleanup`,
      {}
    );
  }
}
