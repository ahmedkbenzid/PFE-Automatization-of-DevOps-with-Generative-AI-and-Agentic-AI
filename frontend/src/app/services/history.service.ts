// history.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface Artifact {
  type: 'cicd' | 'dockerfile' | 'kubernetes' | 'terraform';
  filename: string;
  content: string;
  validation_status: 'passed' | 'failed' | 'skipped' | 'unknown';
  validation_errors: string[];
}

export interface ExecutionLog {
  timestamp: string;
  level: 'info' | 'warning' | 'error' | 'success';
  message: string;
  agent?: string;
}

export interface RepairAttempt {
  attempt_number: number;
  error_detected: string;
  fix_applied: string;
  success: boolean;
}

export interface Session {
  session_id: string;
  prompt: string;
  created_at: string;
  updated_at: string;
  status: 'running' | 'completed' | 'failed';
  artifacts: Artifact[];
  execution_logs: ExecutionLog[];
  repair_attempts: RepairAttempt[];
  rag_sources: string[];
  agents_used: string[];
  duration_seconds: number | null;
  artifact_count: number;
  log_count: number;
}

export interface HistoryStats {
  total: number;
  completed: number;
  failed: number;
  running: number;
  total_artifacts: number;
  avg_duration: number | null;
  repair_rate: number;
}

export interface CreateSessionPayload {
  prompt: string;
  artifacts?: Artifact[];
  execution_logs?: ExecutionLog[];
  repair_attempts?: RepairAttempt[];
  status?: string;
  rag_sources?: string[];
  agents_used?: string[];
  duration_seconds?: number;
}

export interface UpdateSessionPayload {
  artifacts?: Artifact[];
  execution_logs?: ExecutionLog[];
  repair_attempts?: RepairAttempt[];
  status?: string;
  duration_seconds?: number;
}

@Injectable({ providedIn: 'root' })
export class HistoryService {
  private base = `${environment.apiUrl}/api/history`;

  constructor(private http: HttpClient) {}

  getSessions(limit = 50, status?: string): Observable<Session[]> {
    let params = new HttpParams().set('limit', limit);
    if (status) params = params.set('status', status);
    return this.http.get<Session[]>(`${this.base}/sessions`, { params });
  }

  getSession(id: string): Observable<Session> {
    return this.http.get<Session>(`${this.base}/sessions/${id}`);
  }

  createSession(payload: CreateSessionPayload): Observable<Session> {
    return this.http.post<Session>(`${this.base}/sessions`, payload);
  }

  updateSession(id: string, payload: UpdateSessionPayload): Observable<Session> {
    return this.http.patch<Session>(`${this.base}/sessions/${id}`, payload);
  }

  deleteSession(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/sessions/${id}`);
  }

  getStats(): Observable<HistoryStats> {
    return this.http.get<HistoryStats>(`${this.base}/stats`);
  }
}