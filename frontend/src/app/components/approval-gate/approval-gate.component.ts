import { AsyncPipe, NgIf } from '@angular/common';
import { ChangeDetectionStrategy, Component, Input, OnChanges } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { Subject, of } from 'rxjs';
import { catchError, map, startWith, switchMap, tap } from 'rxjs/operators';

import { OrchestratorResult } from '../../models/run.model';
import { ApiService } from '../../services/api.service';

interface ApprovalState {
  submitting: boolean;
  success: string | null;
  error: string | null;
  closed: boolean;
}

@Component({
  selector: 'app-approval-gate',
  standalone: true,
  imports: [NgIf, AsyncPipe, ReactiveFormsModule],
  templateUrl: './approval-gate.component.html',
  styleUrl: './approval-gate.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApprovalGateComponent implements OnChanges {
  @Input() result: OrchestratorResult | null = null;
  @Input() runId = '';

  readonly planText = new FormControl('', { nonNullable: true });

  private readonly actionTrigger$ = new Subject<boolean>();

  readonly actionState$ = this.actionTrigger$.pipe(
    switchMap((approved) =>
      this.api.approveRun(this.runId, approved, approved ? this.parseExecutionOrder(this.planText.value) : []).pipe(
        map((): ApprovalState => ({
          submitting: false,
          success: approved ? 'Continuing execution with approved plan...' : 'Plan rejected. Orchestrator stopping...',
          error: null,
          closed: true,
        })),
        startWith({ submitting: true, success: null, error: null, closed: false }),
        catchError((error) =>
          of({
            submitting: false,
            success: null,
            error: this.describeError(error),
            closed: false,
          }),
        ),
        tap((state) => {
          // Signal that decision was made - modal will close after delay
          if (state.closed) {
            // Modal will auto-hide after 1.5 seconds due to !actionState.closed check
          }
        }),
      ),
    ),
    startWith({ submitting: false, success: null, error: null, closed: false }),
  );

  constructor(private readonly api: ApiService) {}

  ngOnChanges(): void {
    console.log('[ApprovalGate] ngOnChanges called, result:', this.result);
    console.log('[ApprovalGate] isPlanReady():', this.isPlanReady());
    const paragraph = this.planToParagraph(this.result?.execution_plan);
    if (paragraph) {
      this.planText.setValue(paragraph, { emitEvent: false });
    }
  }

  isPlanReady(): boolean {
    const isReady = this.result?.status === 'plan_ready';
    console.log('[ApprovalGate] isPlanReady() check: result.status =', this.result?.status, ', isReady =', isReady);
    return isReady;
  }

  submitDecision(approved: boolean): void {
    if (!this.runId) {
      return;
    }
    this.actionTrigger$.next(approved);
  }

  private parseExecutionOrder(paragraph: string): Array<string | string[]> {
    return paragraph
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => line.replace(/^Step\s*\d+\s*:\s*/i, ''))
      .map((line) => line.split(',').map((agent) => agent.trim()).filter(Boolean))
      .filter((step) => step.length > 0)
      .map((step) => (step.length === 1 ? step[0] : step));
  }

  private planToParagraph(plan: any): string {
    if (!plan || typeof plan !== 'object') {
      return '';
    }

    const executionOrder = Array.isArray(plan.execution_order) ? plan.execution_order : [];
    if (executionOrder.length > 0) {
      return executionOrder
        .map((step: any, index: number) => {
          const line = Array.isArray(step) ? step.join(', ') : String(step);
          return `Step ${index + 1}: ${line}`;
        })
        .join('\n');
    }

    const tasks = Array.isArray(plan.tasks) ? plan.tasks : [];
    if (tasks.length > 0) {
      return tasks
        .map((task: any, index: number) => {
          const value = task?.agent ? String(task.agent) : String(task ?? '');
          return `Step ${index + 1}: ${value}`;
        })
        .join('\n');
    }

    return '';
  }

  private describeError(error: unknown): string {
    if (typeof error === 'object' && error && 'message' in error) {
      return String((error as { message: string }).message);
    }
    return 'Unable to send approval signal.';
  }
}
