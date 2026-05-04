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

type PipelineStepStatus = 'pending' | 'running' | 'completed' | 'failed';

interface PipelineStepView {
  label: string;
  subtitle: string;
  status: PipelineStepStatus;
}

type PipelinePlanEntry = string | string[] | Record<string, unknown>;

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
      <div class="page-header">
        <div>
          <p class="eyebrow">Docker CI/CD Sandbox</p>
          <h1>Execution {{ vm.executionId }}</h1>
        </div>
        <a [routerLink]="['/runs', vm.executionId]" class="back-link">← Open run workspace</a>
      </div>

      <div class="page-layout">
        <aside class="pipeline-sidebar">
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
        </aside>

        <main class="logs-panel">
          <app-cicd-builder [executionId]="vm.executionId"></app-cicd-builder>
        </main>
      </div>
    </div>
  `,
  styles: [`
    .cicd-run-page {
      padding: 24px;
      display: grid;
      gap: 20px;
    }

    .page-header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 4px;
    }

    .eyebrow {
      margin: 0;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #7aa2ff;
      font-size: 12px;
      font-weight: 700;
    }

    h1 {
      margin: 6px 0 0 0;
      color: #fff;
      font-size: 28px;
    }

    .back-link {
      width: fit-content;
      color: #8ab4ff;
      text-decoration: none;
      white-space: nowrap;
    }

    .back-link:hover {
      text-decoration: underline;
    }

    .page-layout {
      display: grid;
      grid-template-columns: minmax(300px, 390px) minmax(0, 1fr);
      gap: 20px;
      align-items: start;
    }

    .pipeline-sidebar {
      display: grid;
      gap: 16px;
      position: sticky;
      top: 24px;
      align-self: start;
    }

    .sidebar-card {
      border: 1px solid var(--border-color, #2c3647);
      background: var(--bg-surface, #111827);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 18px 40px rgba(8, 15, 28, 0.24);
    }

    .hero-card {
      background: linear-gradient(180deg, rgba(20, 34, 57, 0.95) 0%, rgba(13, 23, 40, 0.95) 100%);
    }

    .card-label {
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #8ea4c2;
      font-weight: 700;
      margin-bottom: 10px;
    }

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

    .status-pill.pending {
      background: rgba(142, 164, 194, 0.12);
      color: #c6d3e8;
      border-color: rgba(142, 164, 194, 0.2);
    }

    .status-pill.running {
      background: rgba(13, 140, 255, 0.15);
      color: #72c1ff;
      border-color: rgba(13, 140, 255, 0.3);
    }

    .status-pill.completed {
      background: rgba(0, 170, 0, 0.14);
      color: #8cedab;
      border-color: rgba(0, 170, 0, 0.28);
    }

    .status-pill.failed {
      background: rgba(255, 68, 68, 0.14);
      color: #ff9d9d;
      border-color: rgba(255, 68, 68, 0.3);
    }

    .status-meta {
      color: #b8c7da;
      font-size: 12px;
      font-weight: 600;
    }

    .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }

    .metric {
      border: 1px solid rgba(142, 164, 194, 0.18);
      border-radius: 12px;
      padding: 10px 8px;
      background: rgba(255, 255, 255, 0.03);
      display: grid;
      gap: 4px;
      text-align: center;
    }

    .metric-value {
      font-size: 18px;
      font-weight: 800;
      color: #eef4ff;
    }

    .metric-label {
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #94a8c0;
    }

    .graph-card,
    .note-card {
      background: var(--bg-surface, #111827);
    }

    .pipeline-board {
      display: flex;
      align-items: stretch;
      gap: 10px;
      overflow-x: auto;
      padding-bottom: 4px;
    }

    .pipeline-step {
      min-width: 140px;
      border-radius: 12px;
      padding: 10px 12px;
      border: 1px solid #42536c;
      background: #152235;
      display: grid;
      gap: 4px;
      flex: 0 0 auto;
    }

    .pipeline-step.pending {
      border-color: #42536c;
      background: #152235;
    }

    .pipeline-step.running {
      border-color: #dcaa46;
      background: #3b2b15;
    }

    .pipeline-step.completed {
      border-color: #2da36b;
      background: #123928;
    }

    .pipeline-step.failed {
      border-color: #d0677e;
      background: #44202b;
    }

    .pipeline-step-title {
      font-size: 13px;
      font-weight: 700;
      color: #f0f6ff;
    }

    .pipeline-step-subtitle {
      font-size: 11px;
      color: #bccbde;
      line-height: 1.35;
    }

    .pipeline-arrow {
      display: inline-flex;
      align-items: center;
      color: #7f93ad;
      font-size: 18px;
      font-weight: 700;
    }

    .empty-state {
      border: 1px dashed #3f4b5f;
      border-radius: 12px;
      padding: 14px;
      color: #b7c5d8;
      font-size: 13px;
      line-height: 1.45;
      background: rgba(255, 255, 255, 0.02);
    }

    .note-card p {
      margin: 0;
      color: #d7e2f0;
      line-height: 1.55;
      font-size: 13px;
    }

    .logs-panel {
      min-width: 0;
    }

    @media (max-width: 1100px) {
      .page-layout {
        grid-template-columns: 1fr;
      }

      .pipeline-sidebar {
        position: static;
      }
    }

    @media (max-width: 720px) {
      .metric-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .status-row {
        align-items: flex-start;
        flex-direction: column;
      }
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
      ]).pipe(
        map(([plan, status, execution]) => this.buildViewModel(executionId, plan, status, execution)),
      ),
    ),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  constructor(
    private readonly route: ActivatedRoute,
    private readonly api: ApiService,
  ) {}

  ngOnInit(): void {
    // The observable pipeline drives the view.
  }

  trackStep(_: number, step: PipelineStepView): string {
    return `${step.label}-${step.subtitle}`;
  }

  private buildViewModel(
    executionId: string,
    plan: ExecutionPlanResponse | null,
    status: RunStatusResponse | null,
    execution: ExecutionResultResponse | null,
  ): PipelineSidebarView {
    const executionOrder = this.extractExecutionOrder(plan?.plan);
    const overallStatus = this.resolveOverallStatus(status, execution);
    const steps = executionOrder.map((entry, index) => {
      const stepLabel = this.resolveNodeLabel(entry, index);
      const statusLabel = this.resolveNodeSubtitle(entry, index);
      return {
        label: stepLabel,
        subtitle: statusLabel,
        status: this.resolveCardStatus(index, executionOrder.length, overallStatus),
      };
    });

    const completedSteps = steps.filter((step) => step.status === 'completed').length;
    const runningSteps = steps.filter((step) => step.status === 'running').length;
    const failedSteps = steps.filter((step) => step.status === 'failed').length;
    const plannedSteps = steps.length;
    const progressPercent = plannedSteps > 0 ? Math.round((completedSteps / plannedSteps) * 100) : 0;

    return {
      executionId,
      statusLabel: this.formatStatusLabel(status, execution, plan),
      statusTone: this.statusTone(status, execution),
      complexityScore: plan?.complexity_score ?? 0,
      plannedSteps,
      completedSteps,
      runningSteps,
      failedSteps,
      planOnly: Boolean(plan?.plan_only),
      reasoning: plan?.planner_reasoning || '',
      steps,
      progressPercent,
    };
  }

  private extractExecutionOrder(plan?: ExecutionPlanResponse['plan']): PipelinePlanEntry[] {
    if (!plan || typeof plan !== 'object') {
      return [];
    }

    if (Array.isArray(plan.execution_order) && plan.execution_order.length > 0) {
      return plan.execution_order as PipelinePlanEntry[];
    }

    if (Array.isArray(plan.tasks) && plan.tasks.length > 0) {
      return plan.tasks as PipelinePlanEntry[];
    }

    return [];
  }

  private resolveNodeLabel(entry: PipelinePlanEntry, index: number): string {
    if (Array.isArray(entry)) {
      const labels = entry
        .map((item, itemIndex) => this.resolveNodeLabel(item, itemIndex))
        .filter((label) => label.length > 0);
      return labels.length > 0 ? labels.join(' + ') : `Job ${index + 1}`;
    }

    if (typeof entry === 'string') {
      return this.normalizeJobLabel(entry) || `Job ${index + 1}`;
    }

    const jobFields = ['job_name', 'job', 'jobId', 'job_id', 'title', 'name', 'label', 'id'];
    const rawLabel = this.firstStringValue(entry, jobFields);
    if (rawLabel) {
      return rawLabel;
    }

    const agentLabel = this.firstStringValue(entry, ['agent']);
    return agentLabel ? this.normalizeJobLabel(agentLabel) : `Job ${index + 1}`;
  }

  private resolveNodeSubtitle(entry: PipelinePlanEntry, index: number): string {
    if (Array.isArray(entry) && entry.length > 1) {
      return 'Parallel jobs';
    }

    return `Job ${index + 1}`;
  }

  private firstStringValue(entry: Record<string, unknown>, keys: string[]): string | null {
    for (const key of keys) {
      const value = entry[key];
      if (typeof value === 'string' && value.trim().length > 0) {
        return value.trim();
      }
    }

    return null;
  }

  private normalizeJobLabel(rawLabel: string): string {
    const cleaned = (rawLabel || '').replace(/[_-]+/g, ' ').trim();
    return cleaned.length > 0 ? cleaned : '';
  }

  private resolveOverallStatus(
    status: RunStatusResponse | null,
    execution: ExecutionResultResponse | null,
  ): PipelineStepStatus {
    const returncode = status?.returncode ?? null;
    const executionState = String(execution?.status || '').toLowerCase();

    if (returncode === 0 || executionState === 'completed') {
      return 'completed';
    }

    if ((returncode !== null && returncode !== 0) || executionState === 'error') {
      return 'failed';
    }

    if (executionState === 'running' || executionState === 'pending' || returncode === null) {
      return 'running';
    }

    return 'pending';
  }

  private resolveCardStatus(
    index: number,
    totalSteps: number,
    overallStatus: PipelineStepStatus,
  ): PipelineStepStatus {
    if (overallStatus === 'completed') {
      return 'completed';
    }

    if (overallStatus === 'failed') {
      return index === totalSteps - 1 ? 'failed' : 'completed';
    }

    if (overallStatus === 'running') {
      return index === 0 ? 'running' : 'pending';
    }

    return 'pending';
  }

  private formatStatusLabel(
    status: RunStatusResponse | null,
    execution: ExecutionResultResponse | null,
    plan: ExecutionPlanResponse | null,
  ): string {
    const executionState = String(execution?.status || '').toLowerCase();
    const returncode = status?.returncode ?? null;

    if (returncode === 0 || executionState === 'completed') {
      return 'Completed';
    }

    if ((returncode !== null && returncode !== 0) || executionState === 'error') {
      return 'Failed';
    }

    if (executionState === 'running' || executionState === 'pending' || returncode === null) {
      return plan?.plan_only ? 'Awaiting approval' : 'Running';
    }

    return 'Pending';
  }

  private statusTone(
    status: RunStatusResponse | null,
    execution: ExecutionResultResponse | null,
  ): PipelineStepStatus {
    const executionState = String(execution?.status || '').toLowerCase();
    const returncode = status?.returncode ?? null;

    if (returncode === 0 || executionState === 'completed') {
      return 'completed';
    }

    if ((returncode !== null && returncode !== 0) || executionState === 'error') {
      return 'failed';
    }

    if (executionState === 'running' || executionState === 'pending' || returncode === null) {
      return 'running';
    }

    return 'pending';
  }
}
