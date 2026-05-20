import { AsyncPipe, NgIf, NgFor, NgClass, TitleCasePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, ChangeDetectorRef, Component, ViewChild } from '@angular/core';
import { ActivatedRoute,Router, RouterLink } from '@angular/router';
import { BehaviorSubject, combineLatest, firstValueFrom, interval, of } from 'rxjs';
import {
  catchError,
  distinctUntilChanged,
  filter,
  map,
  scan,
  shareReplay,
  startWith,
  switchMap,
  tap,
} from 'rxjs/operators';

import { AgentStatusComponent } from '../agent-status/agent-status.component';
import { ApprovalGateComponent } from '../approval-gate/approval-gate.component';
import { ActionOptionsComponent, ActionOptionsInput, EditedArtifacts } from '../action-options/action-options.component';
import { RunChatComponent } from '../run-chat/run-chat.component';
import { TerminalPanelComponent } from '../terminal-panel/terminal-panel.component';
import { CompleteEvent, LogEvent, Artifacts } from '../../models/run.model';
import { ApiService, JudgeVerdictResponse } from '../../services/api.service';
import { WebsocketService } from '../../services/websocket.service';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

@Component({
  selector: 'app-run-dashboard',
  standalone: true,
  imports: [
    NgIf,
    NgFor,
    NgClass,
    AsyncPipe,
    TitleCasePipe,
    DecimalPipe,
    RouterLink,
    TerminalPanelComponent,
    AgentStatusComponent,
    ApprovalGateComponent,
    RunChatComponent,
    ActionOptionsComponent,
  ],
  templateUrl: './run-dashboard.component.html',
  styleUrl: './run-dashboard.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RunDashboardComponent {
  readonly activeTab$ = new BehaviorSubject<'logs' | 'workspace' | 'report'>('logs');
  readonly sandboxStarting$ = new BehaviorSubject<boolean>(false);
  readonly sandboxStartError$ = new BehaviorSubject<string | null>(null);

  // ─── LLM Judge state ──────────────────────────────────────────────
  readonly judgeLoading$ = new BehaviorSubject<boolean>(false);
  readonly judgeError$ = new BehaviorSubject<string | null>(null);
  readonly judgeVerdict$ = new BehaviorSubject<JudgeVerdictResponse | null>(null);

  setTab(tab: 'logs' | 'workspace' | 'report'): void {
    this.activeTab$.next(tab);
  }

  /**
   * Request the LLM judge to analyse the logs for the current run.
   * Skips the API call if a cached verdict already exists (unless force=true).
   */
  async requestJudgeVerdict(runId: string, force = false): Promise<void> {
    if (this.judgeLoading$.value) return;

    // Skip if we already have a verdict (and not forcing refresh)
    if (!force && this.judgeVerdict$.value) return;

    this.judgeLoading$.next(true);
    this.judgeError$.next(null);

    try {
      const verdict = await firstValueFrom(
        this.api.judgeRun(runId, force).pipe(
          catchError((err) => {
            const detail = err?.error?.detail || err?.message || 'Failed to get verdict';
            throw new Error(detail);
          }),
        ),
      );
      this.judgeVerdict$.next(verdict);
    } catch (err: any) {
      this.judgeError$.next(err.message || 'Unknown error');
    } finally {
      this.judgeLoading$.next(false);
    }
  }

  readonly runId$ = this.route.paramMap.pipe(
    map((params) => params.get('id') ?? ''),
    filter((id) => id.length > 0),
    distinctUntilChanged(),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  readonly repoPath$  = new BehaviorSubject<string | null>(null);
  readonly githubUrl$ = new BehaviorSubject<string | null>(null);

  readonly editedArtifacts$ = new BehaviorSubject<EditedArtifacts | null>(null);

  @ViewChild(ActionOptionsComponent) actionOptions?: ActionOptionsComponent;

  private readonly wsEvents$ = this.runId$.pipe(
    switchMap((runId) => this.websocket.connect(runId)),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  readonly logs$ = this.wsEvents$.pipe(
    filter((event): event is LogEvent => event.type === 'log'),
    map((event) => event.line),
    scan((lines, line) => [...lines, line], [] as string[]),
    startWith([]),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  readonly planReadyEvent$ = this.logs$.pipe(
    map((lines) => {
      for (let i = lines.length - 1; i >= 0; i--) {
        const line = lines[i];
        if (line && line.includes('plan_ready')) {
          try {
            const parsed = JSON.parse(line);
            if (parsed.status === 'plan_ready') return parsed;
          } catch { /* skip */ }
        }
        if (line && line.includes('=== JSON OUTPUT ===')) {
          for (let j = i + 1; j < Math.min(lines.length, i + 20); j++) {
            const next = lines[j];
            if (next && next.trim().startsWith('{')) {
              try {
                const parsed = JSON.parse(next);
                if (parsed.status === 'plan_ready') return parsed;
              } catch { /* skip */ }
            }
          }
        }
      }
      return null;
    }),
    distinctUntilChanged((prev, curr) => JSON.stringify(prev) === JSON.stringify(curr)),
    tap((event) => {
      if (event && this.activeTab$.value !== 'workspace') {
        this.activeTab$.next('workspace');
      }
    }),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  readonly result$ = this.wsEvents$.pipe(
    filter((event): event is CompleteEvent => event.type === 'complete'),
    map((event) => event.result),
    tap((result) => {
      if (result && this.activeTab$.value !== 'workspace') {
        this.activeTab$.next('workspace');
      }
    }),
    startWith(null),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  readonly approvalResult$ = this.planReadyEvent$.pipe(
    map((planEvent: any) => {
      if (planEvent) {
        return {
          status: 'plan_ready' as const,
          execution_plan: planEvent.execution_plan || {},
          state: planEvent.state || {},
        };
      }
      return null;
    }),
    startWith(null),
  );

  private readonly artifacts$ = combineLatest([this.runId$, this.result$]).pipe(
    switchMap(([runId, result]) => {
      if (!result) return of(null);
      return this.api.getArtifacts(runId).pipe(
        tap((artifacts) => {
          if (artifacts && this.editedArtifacts$.value === null) {
            this.editedArtifacts$.next(this.artifactsToEdited(artifacts));
          }
        }),
        catchError(() => of(null)),
      );
    }),
    startWith(null),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  readonly elapsedSeconds$ = this.runId$.pipe(
    switchMap(() => interval(1000).pipe(startWith(0))),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  readonly actionOptionsInput$ = combineLatest([
    this.editedArtifacts$,
    this.repoPath$,
    this.githubUrl$,
  ]).pipe(
    filter(([editedArtifacts]) => editedArtifacts !== null),
    map(([editedArtifacts, repoPath, githubUrl]) => {
      const input: ActionOptionsInput = {
        repoPathAvailable: !!repoPath,
        githubUrl:         githubUrl   ?? undefined,
        repoPath:          repoPath    ?? undefined,
        editedArtifacts:   editedArtifacts!,
      };
      return input;
    }),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  constructor(
    private readonly route: ActivatedRoute,
    private readonly websocket: WebsocketService,
    private readonly api: ApiService,
    private readonly router: Router,
    private readonly cdr: ChangeDetectorRef,

  ) {
    this.planReadyEvent$.pipe(takeUntilDestroyed()).subscribe();

    // Subscribe to artifacts$ to trigger the side effect (populating editedArtifacts$)
    this.artifacts$.pipe(takeUntilDestroyed()).subscribe();

    this.result$.pipe(
      filter((result) => !!result),
      tap((result) => {
        const repoContext = result?.state?.repo_context;
        if (repoContext?.path)       this.repoPath$.next(repoContext.path);
        if (repoContext?.github_url) this.githubUrl$.next(repoContext.github_url);
      }),
      takeUntilDestroyed(),
    ).subscribe();
  }

  private artifactsToEdited(artifacts: Artifacts): EditedArtifacts {
    return {
      yaml:       artifacts.yaml       || null,
      dockerfile: artifacts.dockerfile || null,
      terraform: {
        main_tf:       artifacts.terraform?.main_tf       || '',
        variables_tf:  artifacts.terraform?.variables_tf  || '',
        outputs_tf:    artifacts.terraform?.outputs_tf    || '',
        providers_tf:  artifacts.terraform?.providers_tf  || '',
      },
      kubernetes: {
        namespace_yaml:   artifacts.kubernetes?.namespace_yaml   || '',
        configmap_yaml:   artifacts.kubernetes?.configmap_yaml   || '',
        secret_yaml:      artifacts.kubernetes?.secret_yaml      || '',
        deployment_yaml:  artifacts.kubernetes?.deployment_yaml  || '',
        service_yaml:     artifacts.kubernetes?.service_yaml     || '',
        ingress_yaml:     artifacts.kubernetes?.ingress_yaml     || '',
        hpa_yaml:         artifacts.kubernetes?.hpa_yaml         || '',
      },
      metadata: artifacts.metadata || {},
    };
  }

  async onArtifactsAccepted(
    runId: string,
    event: { artifacts: EditedArtifacts; applied: boolean },
  ): Promise<void> {
    const nextArtifacts = structuredClone(event.artifacts);
    this.editedArtifacts$.next(nextArtifacts);

    try {
      await firstValueFrom(this.api.saveEditedArtifacts(runId, nextArtifacts as unknown as Record<string, unknown>));
    } catch {
      // Keep local edits even if persistence fails.
    }
  }

  async onChatArtifactsChanged(
    runId: string,
    artifacts: EditedArtifacts,
  ): Promise<void> {
    await this.onArtifactsAccepted(runId, { artifacts, applied: false });
    this.activeTab$.next('workspace');
    this.cdr.markForCheck();
  }

  onArtifactsRejected(): void {
    this.editedArtifacts$.next(null);
  }
  onSandboxExecution(runId: string): void {
    if (this.sandboxStarting$.value) return;

    this.sandboxStarting$.next(true);
    this.sandboxStartError$.next(null);

    const actionDraft = this.actionOptions?.getCurrentDraft();
    const editedArtifacts = actionDraft ?? this.editedArtifacts$.value;
    if (actionDraft) {
      this.editedArtifacts$.next(actionDraft);
    }
    const payload: { force: boolean; artifacts?: Record<string, unknown> } = { force: true };
    if (editedArtifacts) {
      payload.artifacts = editedArtifacts as unknown as Record<string, unknown>;
    }

    this.api.startExecutionForRun(runId, payload).pipe(
      catchError((error) => {
        this.sandboxStartError$.next(this.describeSandboxStartError(error));
        return of(null);
      }),
    ).subscribe((result) => {
      this.sandboxStarting$.next(false);
      if (!result) return;
      void this.router.navigate(['/cicd', runId]);
    });
  }

  private describeSandboxStartError(error: unknown): string {
    if (typeof error === 'object' && error && 'error' in error) {
      const backendError = (error as { error?: { detail?: string } }).error;
      if (backendError && typeof backendError.detail === 'string') {
        return backendError.detail;
      }
    }
    return 'Failed to start sandbox execution.';
  }
}