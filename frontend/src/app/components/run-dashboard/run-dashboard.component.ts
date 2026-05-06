import { AsyncPipe, NgIf } from '@angular/common';
import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { BehaviorSubject, combineLatest, interval, of } from 'rxjs';
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
import { TerminalPanelComponent } from '../terminal-panel/terminal-panel.component';
import { CompleteEvent, LogEvent, Artifacts } from '../../models/run.model';
import { ApiService } from '../../services/api.service';
import { WebsocketService } from '../../services/websocket.service';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

@Component({
  selector: 'app-run-dashboard',
  standalone: true,
  imports: [
    NgIf,
    AsyncPipe,
    RouterLink,
    TerminalPanelComponent,
    AgentStatusComponent,
    ApprovalGateComponent,
    ActionOptionsComponent,
  ],
  templateUrl: './run-dashboard.component.html',
  styleUrl: './run-dashboard.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RunDashboardComponent {
  readonly activeTab$ = new BehaviorSubject<'logs' | 'workspace'>('logs');

  setTab(tab: 'logs' | 'workspace'): void {
    this.activeTab$.next(tab);
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

  onArtifactsAccepted(event: { artifacts: EditedArtifacts; applied: boolean }): void {
    this.editedArtifacts$.next(event.artifacts);
  }

  onArtifactsRejected(): void {
    this.editedArtifacts$.next(null);
  }
}