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
import { ArtifactViewerComponent } from '../artifact-viewer/artifact-viewer.component';
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
    ArtifactViewerComponent,
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

  // Store repo path and github URL (from run request or result)
  readonly repoPath$ = new BehaviorSubject<string | null>(null);
  readonly githubUrl$ = new BehaviorSubject<string | null>(null);

  // Track edited artifacts
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

  // Extract plan_ready event from logs
  readonly planReadyEvent$ = this.logs$.pipe(
    map((lines) => {
      console.log('[DEBUG] Checking logs for plan_ready, total lines:', lines.length);
      // Simply check if ANY line contains "plan_ready"
      for (let i = lines.length - 1; i >= 0; i--) {
        const line = lines[i];
        if (line && line.includes('plan_ready')) {
          console.log('[DEBUG] Found line with plan_ready:', line.substring(0, 200));
          try {
            const parsed = JSON.parse(line);
            if (parsed.status === 'plan_ready') {
              console.log('[DEBUG] Found plan_ready event!', parsed);
              return parsed;
            }
          } catch {
            // Not valid JSON, skip
          }
        }
        // Also check for === JSON OUTPUT === marker
        if (line && line.includes('=== JSON OUTPUT ===')) {
          // Look ahead for JSON
          for (let j = i + 1; j < Math.min(lines.length, i + 20); j++) {
            const nextLine = lines[j];
            if (nextLine && nextLine.trim().startsWith('{')) {
              try {
                const parsed = JSON.parse(nextLine);
                if (parsed.status === 'plan_ready') {
                  console.log('[DEBUG] Found plan_ready via JSON OUTPUT marker!', parsed);
                  return parsed;
                }
              } catch {
                // Not valid JSON, continue
              }
            }
          }
        }
      }
      console.log('[DEBUG] plan_ready NOT found in logs');
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
      console.log('[DEBUG] result$ emitted:', result);
      if (result && this.activeTab$.value !== 'workspace') {
        this.activeTab$.next('workspace');
      }
    }),
    startWith(null),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  // Approval result - show as soon as plan is ready (don't wait for result$)
  readonly approvalResult$ = this.planReadyEvent$.pipe(
    tap((planEvent: any) => {
      console.log('[DEBUG] planReadyEvent$ emitted:', planEvent);
    }),
    map((planEvent: any) => {
      if (planEvent) {
        const result = {
          status: 'plan_ready' as const,
          execution_plan: planEvent.execution_plan || {},
          state: planEvent.state || {},
        };
        console.log('[DEBUG] approvalResult$ returning:', result);
        return result;
      }
      console.log('[DEBUG] approvalResult$ returning null (no planEvent)');
      return null;
    }),
    tap((result: any) => {
      console.log('[DEBUG] approvalResult$ final value:', result);
    }),
    startWith(null),
  );

  readonly artifacts$ = combineLatest([this.runId$, this.result$]).pipe(
    switchMap(([runId, result]) => {
      if (!result) {
        return of(null);
      }
      return this.api.getArtifacts(runId).pipe(
        tap((artifacts) => console.log('[DEBUG] getArtifacts returned:', artifacts)),
        catchError((err) => {
          console.error('[DEBUG] getArtifacts error:', err);
          return of(null);
        })
      );
    }),
    startWith(null),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  readonly elapsedSeconds$ = this.runId$.pipe(
    switchMap(() => interval(1000).pipe(startWith(0))),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  // Generate action options input from artifacts
  readonly actionOptionsInput$ = combineLatest([
    this.artifacts$,
    this.repoPath$,
    this.githubUrl$,
    this.editedArtifacts$,
  ]).pipe(
    map(([artifacts, repoPath, githubUrl, editedArtifacts]) => {
      if (!artifacts) return null;

      const input: ActionOptionsInput = {
        repoPathAvailable: !!repoPath,
        githubUrl: githubUrl ?? undefined,
        repoPath: repoPath ?? undefined,
        editedArtifacts: editedArtifacts || this.artifactsToEdited(artifacts),
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
    // Eagerly subscribe to planReadyEvent$ so the tap side-effect runs
    // even if the user is on the logs tab (where approval gate is hidden).
    this.planReadyEvent$.pipe(takeUntilDestroyed()).subscribe();

    // Extract repo path and github URL from result state
    this.result$.pipe(
      filter((result) => !!result),
      tap((result) => {
        const repoContext = result?.state?.repo_context;
        if (repoContext?.path) {
          this.repoPath$.next(repoContext.path);
        }
        if (repoContext?.github_url) {
          this.githubUrl$.next(repoContext.github_url);
        }
      }),
      takeUntilDestroyed(),
    ).subscribe();
  }

  /**
   * Convert Artifacts model to EditedArtifacts format
   */
  private artifactsToEdited(artifacts: Artifacts): EditedArtifacts {
    return {
      yaml: artifacts.yaml || null,
      dockerfile: artifacts.dockerfile || null,
      terraform: {
        main_tf: artifacts.terraform?.main_tf || '',
        variables_tf: artifacts.terraform?.variables_tf || '',
        outputs_tf: artifacts.terraform?.outputs_tf || '',
        providers_tf: artifacts.terraform?.providers_tf || '',
      },
      kubernetes: {
        namespace_yaml: artifacts.kubernetes?.namespace_yaml || '',
        configmap_yaml: artifacts.kubernetes?.configmap_yaml || '',
        secret_yaml: artifacts.kubernetes?.secret_yaml || '',
        deployment_yaml: artifacts.kubernetes?.deployment_yaml || '',
        service_yaml: artifacts.kubernetes?.service_yaml || '',
        ingress_yaml: artifacts.kubernetes?.ingress_yaml || '',
        hpa_yaml: artifacts.kubernetes?.hpa_yaml || '',
      },
      metadata: artifacts.metadata || {},
    };
  }

  /**
   * Handle artifacts accepted event
   */
  onArtifactsAccepted(event: { artifacts: EditedArtifacts; applied: boolean }): void {
    console.log('✅ Artifacts accepted:', event);
    this.editedArtifacts$.next(event.artifacts);
    if (event.applied) {
      // Show success message or navigate to repo
      console.log('📁 Artifacts applied to repository');
    } else {
      console.log('📥 Artifacts prepared for download');
    }
  }

  /**
   * Handle artifacts rejected event
   */
  onArtifactsRejected(): void {
    console.log('❌ Artifacts rejected');
    this.editedArtifacts$.next(null);
  }
}
