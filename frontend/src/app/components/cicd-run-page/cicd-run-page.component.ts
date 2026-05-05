import { AsyncPipe, CommonModule, NgClass, NgFor, NgIf } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { combineLatest, Observable, of } from 'rxjs';
import { catchError, distinctUntilChanged, filter, map, shareReplay, switchMap } from 'rxjs/operators';

import { CicdBuilderComponent } from '../cicd-builder/cicd-builder.component';
import {
  ApiService,
  ExecutionPlanResponse,
  ExecutionResultResponse,
  RunStatusResponse,
} from '../../services/api.service';

import { Artifacts } from '../../models/run.model';

type PipelineStepStatus = 'pending' | 'running' | 'completed' | 'failed';

interface PipelineStepView {
  label: string;
  subtitle: string;
  status: PipelineStepStatus;
}

type PipelinePlanEntry = string | string[] | Record<string, unknown>;

interface JobNode {
  id: string;
  needs: string[];
}

interface PipelineSidebarView {
  executionId: string;
  statusLabel: string;
  statusTone: PipelineStepStatus;
  complexityScore: number;
  plannedSteps: number;
  completedSteps: number;
  runningSteps: number;
  failedSteps: number;
  planOnly: boolean;
  reasoning: string;
  steps: PipelineStepView[];
  progressPercent: number;
}

@Component({
  selector: 'app-cicd-run-page',
  standalone: true,
  imports: [CommonModule, AsyncPipe, NgIf, NgFor, NgClass, RouterLink, CicdBuilderComponent],
  template: `
    <div class="cicd-run-page" *ngIf="viewModel$ | async as vm">

      <!-- Page header -->
      <div class="page-header">
        <div>
          <p class="eyebrow">Docker CI/CD Sandbox</p>
          <h1>Execution {{ vm.executionId }}</h1>
        </div>
        <a [routerLink]="['/runs', vm.executionId]" class="back-link">← Open run workspace</a>
      </div>

      <!-- Pipeline cards — full width -->
      <div class="pipeline-section">

        <section class="sidebar-card hero-card">
          <div class="card-label">Pipeline status</div>
          <div class="status-row">
            <span class="status-pill" [ngClass]="vm.statusTone">{{ vm.statusLabel }}</span>
            <span class="status-meta">{{ vm.progressPercent }}% complete</span>
          </div>
          <div class="metric-grid">
            <div class="metric">
              <span class="metric-value">{{ vm.plannedSteps }}</span>
              <span class="metric-label">Steps</span>
            </div>
            <div class="metric">
              <span class="metric-value">{{ vm.completedSteps }}</span>
              <span class="metric-label">Done</span>
            </div>
            <div class="metric">
              <span class="metric-value">{{ vm.runningSteps }}</span>
              <span class="metric-label">Running</span>
            </div>
            <div class="metric">
              <span class="metric-value">{{ vm.failedSteps }}</span>
              <span class="metric-label">Failed</span>
            </div>
          </div>
        </section>

        <section class="sidebar-card graph-card">
          <div class="card-label">Pipeline graph</div>
          <div class="pipeline-board" *ngIf="vm.steps.length > 0; else noSteps">
            <ng-container *ngFor="let step of vm.steps; let last = last; trackBy: trackStep">
              <article class="pipeline-step" [ngClass]="step.status">
                <div class="pipeline-step-title">{{ step.label }}</div>
                <div class="pipeline-step-subtitle">{{ step.subtitle }}</div>
              </article>
              <div class="pipeline-arrow" *ngIf="!last">→</div>
            </ng-container>
          </div>
          <ng-template #noSteps>
            <div class="empty-state">
              No execution plan is available yet. Run the workflow once to populate the graph.
            </div>
          </ng-template>
        </section>

        <section class="sidebar-card note-card" *ngIf="vm.reasoning">
          <div class="card-label">Planner reasoning</div>
          <p>{{ vm.reasoning }}</p>
        </section>

        <section class="sidebar-card note-card" *ngIf="vm.planOnly">
          <div class="card-label">Plan only</div>
          <p>This run is paused for approval before execution.</p>
        </section>

      </div>

      <!-- Execution Sandbox Logs — full width below pipeline -->
      <section class="logs-section">
        <div class="logs-section-header">
          <span class="logs-section-dot"></span>
          <span class="logs-section-title">Execution Sandbox Logs</span>
          <span class="logs-section-badge" [ngClass]="vm.statusTone">{{ vm.statusLabel }}</span>
        </div>
        <!-- cicd-builder renders its summary-bar + terminal directly here, no extra wrapper -->
        <app-cicd-builder [executionId]="vm.executionId"></app-cicd-builder>
      </section>

    </div>
  `,
  styles: [`
    .cicd-run-page {
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }

    /* ── Header ─────────────────────────────────────────────── */
    .page-header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
    }

    .eyebrow {
      margin: 0;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #7aa2ff;
      font-size: 12px;
      font-weight: 700;
    }

    h1 { margin: 6px 0 0; color: #fff; font-size: 28px; }

    .back-link { color: #8ab4ff; text-decoration: none; white-space: nowrap; }
    .back-link:hover { text-decoration: underline; }

    /* ── Pipeline section ───────────────────────────────────── */
    .pipeline-section {
      display: flex;
      flex-direction: column;
      gap: 16px;
      width: 100%;
    }

    /* ── Shared card base ───────────────────────────────────── */
    .sidebar-card {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--border-color, #2c3647);
      background: var(--bg-surface, #111827);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 18px 40px rgba(8,15,28,0.24);
    }

    .hero-card {
      background: linear-gradient(180deg, rgba(20,34,57,0.95) 0%, rgba(13,23,40,0.95) 100%);
    }

    .graph-card,
    .note-card { background: var(--bg-surface, #111827); }

    .card-label {
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #8ea4c2;
      font-weight: 700;
      margin-bottom: 10px;
    }

    /* ── Status row ─────────────────────────────────────────── */
    .status-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 6px 12px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      border: 1px solid transparent;
    }

    .status-pill.pending   { background: rgba(142,164,194,0.12); color: #c6d3e8; border-color: rgba(142,164,194,0.2); }
    .status-pill.running   { background: rgba(13,140,255,0.15);  color: #72c1ff; border-color: rgba(13,140,255,0.3); }
    .status-pill.completed { background: rgba(0,170,0,0.14);     color: #8cedab; border-color: rgba(0,170,0,0.28); }
    .status-pill.failed    { background: rgba(255,68,68,0.14);   color: #ff9d9d; border-color: rgba(255,68,68,0.3); }

    .status-meta { color: #b8c7da; font-size: 12px; font-weight: 600; }

    /* ── Metric grid ────────────────────────────────────────── */
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 10px;
    }

    .metric {
      border: 1px solid rgba(142,164,194,0.18);
      border-radius: 12px;
      padding: 10px 8px;
      background: rgba(255,255,255,0.03);
      display: grid;
      gap: 4px;
      text-align: center;
    }

    .metric-value { font-size: 18px; font-weight: 800; color: #eef4ff; }
    .metric-label { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: #94a8c0; }

    /* ── Pipeline graph ─────────────────────────────────────── */
    .pipeline-board {
      display: flex;
      align-items: stretch;
      flex-wrap: wrap;
      gap: 10px;
      padding-bottom: 4px;
    }

    .pipeline-step {
      min-width: 160px;
      max-width: 220px;
      flex: 1 1 160px;
      border-radius: 12px;
      padding: 12px 16px;
      border: 1px solid #42536c;
      background: #152235;
      display: grid;
      gap: 4px;
    }

    .pipeline-step.pending   { border-color: #42536c; background: #152235; }
    .pipeline-step.running   { border-color: #dcaa46; background: #3b2b15; }
    .pipeline-step.completed { border-color: #2da36b; background: #123928; }
    .pipeline-step.failed    { border-color: #d0677e; background: #44202b; }

    .pipeline-step-title    { font-size: 13px; font-weight: 700; color: #f0f6ff; }
    .pipeline-step-subtitle { font-size: 11px; color: #bccbde; line-height: 1.35; }

    .pipeline-arrow {
      display: inline-flex;
      align-items: center;
      color: #7f93ad;
      font-size: 18px;
      font-weight: 700;
      flex: 0 0 auto;
    }

    .empty-state {
      border: 1px dashed #3f4b5f;
      border-radius: 12px;
      padding: 14px;
      color: #b7c5d8;
      font-size: 13px;
      line-height: 1.45;
      background: rgba(255,255,255,0.02);
    }

    .note-card p { margin: 0; color: #d7e2f0; line-height: 1.55; font-size: 13px; }

    /* ── Execution Sandbox Logs section ─────────────────────── */
    .logs-section {
      border: 1px solid #2c3647;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 18px 40px rgba(8,15,28,0.28);
    }

    .logs-section-header {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 18px;
      background: linear-gradient(90deg, #0d1a2e 0%, #111f35 100%);
      border-bottom: 1px solid #1e2d42;
    }

    /* Small coloured dot instead of emoji */
    .logs-section-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #3a8fd4;
      flex-shrink: 0;
    }

    .logs-section-title {
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #c8d9f0;
      flex: 1;
    }

    .logs-section-badge {
      display: inline-flex;
      align-items: center;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      border: 1px solid transparent;
    }

    .logs-section-badge.pending   { background: rgba(142,164,194,0.12); color: #c6d3e8; border-color: rgba(142,164,194,0.2); }
    .logs-section-badge.running   { background: rgba(13,140,255,0.15);  color: #72c1ff; border-color: rgba(13,140,255,0.3); }
    .logs-section-badge.completed { background: rgba(0,170,0,0.14);     color: #8cedab; border-color: rgba(0,170,0,0.28); }
    .logs-section-badge.failed    { background: rgba(255,68,68,0.14);   color: #ff9d9d; border-color: rgba(255,68,68,0.3); }

    /* ── Responsive ─────────────────────────────────────────── */
    @media (max-width: 720px) {
      .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .status-row  { align-items: flex-start; flex-direction: column; }
    }
  `],
})
export class CicdRunPageComponent implements OnInit {
  readonly executionId$ = this.route.paramMap.pipe(
    map((params) => params.get('id') ?? ''),
    filter((id) => id.length > 0),
    distinctUntilChanged(),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  readonly viewModel$: Observable<PipelineSidebarView> = this.executionId$.pipe(
    switchMap((executionId) =>
      combineLatest([
        this.api.getExecutionPlan(executionId).pipe(catchError(() => of(null))),
        this.api.getStatus(executionId).pipe(catchError(() => of(null))),
        this.api.getExecution(executionId).pipe(catchError(() => of(null))),
        this.api.getArtifacts(executionId).pipe(catchError(() => of(null))),
      ]).pipe(
        map(([plan, status, execution, artifacts]) =>
          this.buildViewModel(executionId, plan, status, execution, artifacts),
        ),
      ),
    ),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  constructor(
    private readonly route: ActivatedRoute,
    private readonly api: ApiService,
  ) {}

  ngOnInit(): void {}

  trackStep(_: number, step: PipelineStepView): string {
    return `${step.label}-${step.subtitle}`;
  }

  private buildViewModel(
    executionId: string,
    plan: ExecutionPlanResponse | null,
    status: RunStatusResponse | null,
    execution: ExecutionResultResponse | null,
    artifacts: Artifacts | null = null,
  ): PipelineSidebarView {
    const overallStatus = this.resolveOverallStatus(status, execution);

    const jobNodes = this.parseJobGraphFromYaml(artifacts?.yaml || null);
    const orderedJobs = jobNodes.length > 0
      ? this.topologicalSort(jobNodes)
      : this.extractExecutionOrder(plan?.plan).map((entry, i) => ({
          id: this.resolveNodeLabel(entry, i),
          needs: [],
        }));

    const steps: PipelineStepView[] = orderedJobs.map((job, index) => ({
      label: this.normalizeJobLabel(job.id),
      subtitle: job.needs.length > 0
        ? `needs: ${job.needs.map((n) => this.normalizeJobLabel(n)).join(', ')}`
        : 'no dependencies',
      status: this.resolveCardStatusByPosition(index, orderedJobs.length, overallStatus),
    }));

    const completedSteps  = steps.filter((s) => s.status === 'completed').length;
    const runningSteps    = steps.filter((s) => s.status === 'running').length;
    const failedSteps     = steps.filter((s) => s.status === 'failed').length;
    const plannedSteps    = steps.length;
    const progressPercent = plannedSteps > 0
      ? Math.round((completedSteps / plannedSteps) * 100) : 0;

    return {
      executionId,
      statusLabel:    this.formatStatusLabel(status, execution, plan),
      statusTone:     this.statusTone(status, execution),
      complexityScore: plan?.complexity_score ?? 0,
      plannedSteps,
      completedSteps,
      runningSteps,
      failedSteps,
      planOnly:    Boolean(plan?.plan_only),
      reasoning:   plan?.planner_reasoning || '',
      steps,
      progressPercent,
    };
  }

  // ─── YAML DAG Parser ────────────────────────────────────────────────────────

  private parseJobGraphFromYaml(yamlText: string | null): JobNode[] {
    if (!yamlText) return [];
    const lines  = yamlText.split(/\r?\n/);
    const nodes: JobNode[] = [];
    let inJobs   = false;
    let currentJob: JobNode | null = null;
    let inNeeds  = false;

    for (const raw of lines) {
      const line = raw.trimRight();

      if (!inJobs) {
        if (/^jobs:\s*$/.test(line)) inJobs = true;
        continue;
      }
      if (/^[^\s].+:/.test(line)) {
        if (currentJob) nodes.push(currentJob);
        currentJob = null; inJobs = false; break;
      }

      const jobMatch = line.match(/^  ([a-zA-Z0-9_-]+):\s*$/);
      if (jobMatch) {
        if (currentJob) nodes.push(currentJob);
        currentJob = { id: jobMatch[1], needs: [] };
        inNeeds = false; continue;
      }

      if (!currentJob) continue;

      const inlineNeeds = line.match(/^\s+needs:\s+(.+)$/);
      if (inlineNeeds) {
        inNeeds = false;
        const raw = inlineNeeds[1].trim().replace(/[\[\]]/g, '');
        currentJob.needs = raw.split(',').map((s) => s.trim()).filter((s) => s.length > 0);
        continue;
      }
      if (/^\s+needs:\s*$/.test(line)) { inNeeds = true; continue; }
      if (inNeeds) {
        const item = line.match(/^\s+-\s+(.+)$/);
        if (item) { currentJob.needs.push(item[1].trim()); continue; }
        inNeeds = false;
      }
    }

    if (currentJob) nodes.push(currentJob);
    return nodes;
  }

  private topologicalSort(nodes: JobNode[]): JobNode[] {
    const nodeMap  = new Map<string, JobNode>(nodes.map((n) => [n.id, n]));
    const inDegree = new Map<string, number>(nodes.map((n) => [n.id, 0]));

    for (const node of nodes)
      for (const dep of node.needs)
        if (nodeMap.has(dep)) inDegree.set(node.id, (inDegree.get(node.id) ?? 0) + 1);

    const queue  = nodes.filter((n) => (inDegree.get(n.id) ?? 0) === 0);
    const sorted: JobNode[] = [];

    while (queue.length > 0) {
      queue.sort((a, b) => a.id.localeCompare(b.id));
      const current = queue.shift()!;
      sorted.push(current);
      for (const node of nodes) {
        if (node.needs.includes(current.id)) {
          const d = (inDegree.get(node.id) ?? 1) - 1;
          inDegree.set(node.id, d);
          if (d === 0) queue.push(node);
        }
      }
    }

    const seen = new Set(sorted.map((n) => n.id));
    for (const node of nodes) if (!seen.has(node.id)) sorted.push(node);
    return sorted;
  }

  // ─── Fallback plan parser ────────────────────────────────────────────────────

  private extractExecutionOrder(plan?: ExecutionPlanResponse['plan']): PipelinePlanEntry[] {
    if (!plan || typeof plan !== 'object') return [];
    if (Array.isArray(plan.execution_order) && plan.execution_order.length > 0)
      return plan.execution_order as PipelinePlanEntry[];
    if (Array.isArray(plan.tasks) && plan.tasks.length > 0)
      return plan.tasks as PipelinePlanEntry[];
    return [];
  }

  private resolveNodeLabel(entry: PipelinePlanEntry, index: number): string {
    if (Array.isArray(entry)) {
      const labels = entry.map((item, i) => this.resolveNodeLabel(item, i)).filter((l) => l.length > 0);
      return labels.length > 0 ? labels.join(' + ') : `Job ${index + 1}`;
    }
    if (typeof entry === 'string') return this.normalizeJobLabel(entry) || `Job ${index + 1}`;
    const jobFields = ['job_name', 'job', 'jobId', 'job_id', 'title', 'name', 'label', 'id'];
    const rawLabel  = this.firstStringValue(entry, jobFields);
    if (rawLabel) return rawLabel;
    const agentLabel = this.firstStringValue(entry, ['agent']);
    return agentLabel ? this.normalizeJobLabel(agentLabel) : `Job ${index + 1}`;
  }

  private firstStringValue(entry: Record<string, unknown>, keys: string[]): string | null {
    for (const key of keys) {
      const value = entry[key];
      if (typeof value === 'string' && value.trim().length > 0) return value.trim();
    }
    return null;
  }

  // ─── Status helpers ──────────────────────────────────────────────────────────

  private resolveOverallStatus(
    status: RunStatusResponse | null,
    execution: ExecutionResultResponse | null,
  ): PipelineStepStatus {
    const returncode     = status?.returncode ?? null;
    const executionState = String(execution?.status || '').toLowerCase();
    if (returncode === 0 || executionState === 'completed') return 'completed';
    if ((returncode !== null && returncode !== 0) || executionState === 'error') return 'failed';
    if (executionState === 'running' || executionState === 'pending' || returncode === null) return 'running';
    return 'pending';
  }

  private resolveCardStatusByPosition(
    index: number, totalSteps: number, overallStatus: PipelineStepStatus,
  ): PipelineStepStatus {
    if (overallStatus === 'completed') return 'completed';
    if (overallStatus === 'failed')    return index < totalSteps - 1 ? 'completed' : 'failed';
    if (overallStatus === 'running')   return index === 0 ? 'running' : 'pending';
    return 'pending';
  }

  private formatStatusLabel(
    status: RunStatusResponse | null,
    execution: ExecutionResultResponse | null,
    plan: ExecutionPlanResponse | null,
  ): string {
    const executionState = String(execution?.status || '').toLowerCase();
    const returncode     = status?.returncode ?? null;
    if (returncode === 0 || executionState === 'completed') return 'Completed';
    if ((returncode !== null && returncode !== 0) || executionState === 'error') return 'Failed';
    if (executionState === 'running' || executionState === 'pending' || returncode === null)
      return plan?.plan_only ? 'Awaiting approval' : 'Running';
    return 'Pending';
  }

  private statusTone(
    status: RunStatusResponse | null,
    execution: ExecutionResultResponse | null,
  ): PipelineStepStatus {
    const executionState = String(execution?.status || '').toLowerCase();
    const returncode     = status?.returncode ?? null;
    if (returncode === 0 || executionState === 'completed') return 'completed';
    if ((returncode !== null && returncode !== 0) || executionState === 'error') return 'failed';
    if (executionState === 'running' || executionState === 'pending' || returncode === null) return 'running';
    return 'pending';
  }

  private normalizeJobLabel(rawLabel: string): string {
    return (rawLabel || '').replace(/[_-]+/g, ' ').trim();
  }
}