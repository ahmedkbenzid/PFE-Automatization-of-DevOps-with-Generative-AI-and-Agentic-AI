import { AsyncPipe, NgClass, NgFor, NgIf } from '@angular/common';
import {
  AfterViewChecked,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  SimpleChanges,
  ViewChild,
} from '@angular/core';
import { environment } from '../../../environments/environment';
import { BehaviorSubject, Observable, Subject, combineLatest, defer, of, timer } from 'rxjs';
import {
  catchError,
  delayWhen,
  map,
  repeat,
  retryWhen,
  scan,
  shareReplay,
  startWith,
  switchMap,
  takeUntil,
} from 'rxjs/operators';
import { webSocket } from 'rxjs/webSocket';

type StageName = 'checkout' | 'build' | 'test' | 'docker push';
type StageStatus = 'pending' | 'running' | 'done' | 'failed';
type LogLevel = 'info' | 'warn' | 'error';
type ConnectionState = 'idle' | 'connecting' | 'live' | 'disconnected';

interface SandboxSocketMessage {
  run_id: string;
  stage: string;
  line: string;
  level: LogLevel;
  elapsed_ms: number;
  stage_status: StageStatus;
  type?: string;
  result?: string;
}

interface TerminalLine {
  id: number;
  stage: StageName;
  line: string;
  level: LogLevel;
  elapsedMs: number;
}

interface SandboxPanelState {
  runId: string;
  stages: Record<StageName, StageStatus>;
  terminal: TerminalLine[];
  terminalSeq: number;
  failedStage: StageName | null;
  completedCount: number;
  progressPercent: number;
  hasFailure: boolean;
  connectionState: ConnectionState;
}

const STAGE_ORDER: StageName[] = ['checkout', 'build', 'test', 'docker push'];
const MAX_TERMINAL_LINES = 500;

function createInitialState(runId: string): SandboxPanelState {
  return {
    runId,
    stages: {
      checkout: 'pending',
      build: 'pending',
      test: 'pending',
      'docker push': 'pending',
    },
    terminal: [],
    terminalSeq: 0,
    failedStage: null,
    completedCount: 0,
    progressPercent: 0,
    hasFailure: false,
    connectionState: runId ? 'connecting' : 'idle',
  };
}

@Component({
  selector: 'app-sandbox-panel',
  standalone: true,
  imports: [NgIf, NgFor, NgClass, AsyncPipe],
  templateUrl: './sandbox-panel.component.html',
  styleUrls: ['./sandbox-panel.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SandboxPanelComponent implements OnChanges, OnDestroy, AfterViewChecked {
  @Input() runId: string | null = null;
  @Input() wsEndpointBase = `${environment.wsUrl.replace(/\/$/, '')}/ws/execution`;

  @Output() repairRequested = new EventEmitter<{ runId: string; failedStage: StageName }>();

  @ViewChild('terminalPane') private terminalPane?: ElementRef<HTMLDivElement>;

  readonly stageOrder = STAGE_ORDER;

  private readonly destroy$ = new Subject<void>();
  private readonly runIdSource$ = new BehaviorSubject<string | null>(null);
  private readonly wsBaseSource$ = new BehaviorSubject<string>(`${environment.wsUrl.replace(/\/$/, '')}/ws/execution`);

  private lastRenderedLineCount = 0;

  readonly panelState$: Observable<SandboxPanelState> = combineLatest([
    this.runIdSource$,
    this.wsBaseSource$,
  ]).pipe(
    switchMap(([runId, wsBase]) => {
      if (!runId) {
        return of(createInitialState(''));
      }

      const initial = createInitialState(runId);
      return this.createSocketStream(runId, wsBase).pipe(
        scan((state, message) => this.reduceState(state, message), initial),
        startWith(initial),
        catchError((error) => of(this.applySocketError(initial, String(error ?? 'unknown error')))),
      );
    }),
    takeUntil(this.destroy$),
    shareReplay({ bufferSize: 1, refCount: true }),
  );

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['runId']) {
      this.runIdSource$.next(this.runId ?? null);
    }
    if (changes['wsEndpointBase']) {
      this.wsBaseSource$.next(this.wsEndpointBase || `${environment.wsUrl.replace(/\/$/, '')}/ws/execution`);
      if (this.runId) {
        this.runIdSource$.next(this.runId);
      }
    }
  }

  ngAfterViewChecked(): void {
    const pane = this.terminalPane?.nativeElement;
    if (!pane) {
      return;
    }

    const currentLineCount = pane.querySelectorAll('.terminal-line').length;
    if (currentLineCount !== this.lastRenderedLineCount) {
      pane.scrollTop = pane.scrollHeight;
      this.lastRenderedLineCount = currentLineCount;
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onTriggerRepair(runId: string, failedStage: StageName | null): void {
    if (!runId || !failedStage) {
      return;
    }
    this.repairRequested.emit({ runId, failedStage });
  }

  stageIcon(status: StageStatus): string {
    if (status === 'done') {
      return 'check_circle';
    }
    if (status === 'running') {
      return 'hourglass_top';
    }
    if (status === 'failed') {
      return 'error';
    }
    return 'radio_button_unchecked';
  }

  trackStage(_: number, stage: StageName): string {
    return stage;
  }

  trackTerminal(_: number, line: TerminalLine): number {
    return line.id;
  }

  private createSocketStream(runId: string, wsEndpointBase: string): Observable<SandboxSocketMessage> {
    const base = wsEndpointBase.replace(/\/$/, '');
    const wsUrl = `${base}/${encodeURIComponent(runId)}`;

    return defer(() =>
      webSocket<SandboxSocketMessage>({
        url: wsUrl,
        deserializer: ({ data }) => {
          if (typeof data === 'string') {
            return JSON.parse(data) as SandboxSocketMessage;
          }
          return data as SandboxSocketMessage;
        },
      }),
    ).pipe(
      retryWhen((errors) =>
        errors.pipe(
          scan((attempt) => attempt + 1, 0),
          delayWhen((attempt) => timer(this.reconnectDelayMs(attempt))),
        ),
      ),
      repeat({
        delay: (attempt) => timer(this.reconnectDelayMs(attempt)),
      }),
    );
  }

  private reconnectDelayMs(attempt: number): number {
    const safeAttempt = Math.max(0, attempt);
    return Math.min(1000 * (2 ** safeAttempt), 30000);
  }

  private reduceState(state: SandboxPanelState, message: SandboxSocketMessage): SandboxPanelState {
    const normalizedStage = this.normalizeStage(message.stage, state.failedStage ?? undefined);
    const nextStages = { ...state.stages };

    if (normalizedStage) {
      nextStages[normalizedStage] = message.stage_status;
    }

    const nextFailedStage =
      message.stage_status === 'failed' && normalizedStage
        ? normalizedStage
        : state.failedStage;

    const nextLine: TerminalLine = {
      id: state.terminalSeq + 1,
      stage: normalizedStage || state.failedStage || 'build',
      line: message.line,
      level: message.level,
      elapsedMs: message.elapsed_ms,
    };

    const nextTerminal = state.terminal.length >= MAX_TERMINAL_LINES
      ? [...state.terminal.slice(1), nextLine]
      : [...state.terminal, nextLine];

    const completedCount = STAGE_ORDER.filter((stage) => {
      const status = nextStages[stage];
      return status === 'done' || status === 'failed';
    }).length;

    return {
      ...state,
      stages: nextStages,
      terminalSeq: nextLine.id,
      terminal: nextTerminal,
      failedStage: nextFailedStage,
      hasFailure: Boolean(nextFailedStage),
      completedCount,
      progressPercent: Math.round((completedCount / STAGE_ORDER.length) * 100),
      connectionState: 'live',
    };
  }

  private applySocketError(state: SandboxPanelState, errorMessage: string): SandboxPanelState {
    const fallbackLine: TerminalLine = {
      id: state.terminalSeq + 1,
      stage: state.failedStage || 'build',
      line: `WebSocket disconnected: ${errorMessage}`,
      level: 'error',
      elapsedMs: 0,
    };

    const nextTerminal = state.terminal.length >= MAX_TERMINAL_LINES
      ? [...state.terminal.slice(1), fallbackLine]
      : [...state.terminal, fallbackLine];

    return {
      ...state,
      terminalSeq: fallbackLine.id,
      terminal: nextTerminal,
      connectionState: 'disconnected',
    };
  }

  private normalizeStage(rawStage: string, fallback?: StageName): StageName | null {
    const value = String(rawStage || '').trim().toLowerCase();
    if (!value) {
      return fallback || null;
    }

    if (value === 'checkout') {
      return 'checkout';
    }
    if (value === 'build') {
      return 'build';
    }
    if (value === 'test') {
      return 'test';
    }
    if (value === 'docker push' || value === 'docker_push' || value === 'push') {
      return 'docker push';
    }

    return fallback || null;
  }
}
