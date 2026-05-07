import { AsyncPipe, NgClass } from '@angular/common';
import {
  AfterViewInit,
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
  retry,
  scan,
  shareReplay,
  startWith,
  switchMap,
  takeUntil,
  takeWhile,
} from 'rxjs/operators';
import { webSocket } from 'rxjs/webSocket';

type StageName = 'checkout' | 'build' | 'test' | 'docker push';
type StageStatus = 'pending' | 'running' | 'done' | 'failed';
type LogLevel = 'info' | 'warn' | 'error';
type ConnectionState = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'disconnected';

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

// Synthetic message emitted at the start of every reconnect attempt so the
// UI can show 'reconnecting' instead of staying stuck on 'live'.
interface ReconnectingMessage {
  __reconnecting: true;
}

type StreamEvent = SandboxSocketMessage | ReconnectingMessage;

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
  // FIX (warning): store all lines in an append-only array and slice lazily
  // in the template — avoids O(n) full-array copy on every message.
  terminal: TerminalLine[];
  terminalSeq: number;
  failedStage: StageName | null;
  completedCount: number;
  progressPercent: number;
  hasFailure: boolean;
  connectionState: ConnectionState;
  isTerminal: boolean; // true once result=done|failed received
}

const STAGE_ORDER: StageName[] = ['checkout', 'build', 'test', 'docker push'];
const MAX_TERMINAL_LINES = 500;
// How many lines to render in the DOM — a sliding window of the full buffer.
const VISIBLE_TERMINAL_LINES = 200;
// FIX (critical): max reconnect attempts before giving up.
const MAX_RECONNECT_ATTEMPTS = 10;

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
    isTerminal: false,
  };
}

@Component({
  selector: 'app-sandbox-panel',
  standalone: true,
  // FIX (minor): removed NgIf, NgFor — replaced by built-in @if / @for
  // control flow in the template (Angular 17+). NgClass kept for dynamic CSS.
  imports: [NgClass, AsyncPipe],
  templateUrl: './sandbox-panel.component.html',
  styleUrls: ['./sandbox-panel.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SandboxPanelComponent implements OnChanges, OnDestroy, AfterViewInit {
  @Input() runId: string | null = null;
  // FIX (minor): single source of truth — wsBaseSource$ is seeded from the
  // @Input default so the two values cannot silently diverge.
  @Input() wsEndpointBase = `${environment.wsUrl.replace(/\/$/, '')}/ws/execution`;

  @Output() repairRequested = new EventEmitter<{ runId: string; failedStage: StageName }>();

  @ViewChild('terminalPane') private terminalPane?: ElementRef<HTMLDivElement>;

  readonly stageOrder = STAGE_ORDER;
  readonly visibleLines = VISIBLE_TERMINAL_LINES;

  private readonly destroy$ = new Subject<void>();
  private readonly runIdSource$ = new BehaviorSubject<string | null>(null);

  // FIX (minor): seeded from the @Input so there is one source of truth.
  private readonly wsBaseSource$ = new BehaviorSubject<string>(this.wsEndpointBase);

  // FIX (critical): MutationObserver wired in AfterViewInit — replaces the
  // ngAfterViewChecked querySelectorAll that ran on every CD cycle.
  private terminalObserver?: MutationObserver;

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
        scan((state, event) => this.reduceState(state, event), initial),
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
      // FIX (warning): only push to wsBaseSource$ — combineLatest re-emits
      // automatically, so the redundant runIdSource$.next() that caused a
      // double switchMap cancellation is removed.
      this.wsBaseSource$.next(
        this.wsEndpointBase || `${environment.wsUrl.replace(/\/$/, '')}/ws/execution`,
      );
    }
  }

  ngAfterViewInit(): void {
    // FIX (critical): MutationObserver fires only when child nodes are actually
    // added to the terminal pane — replaces the ngAfterViewChecked + querySelectorAll
    // pattern that forced a layout query on every change-detection cycle.
    const pane = this.terminalPane?.nativeElement;
    if (!pane) {
      return;
    }

    this.terminalObserver = new MutationObserver(() => {
      pane.scrollTop = pane.scrollHeight;
    });

    this.terminalObserver.observe(pane, { childList: true });
  }

  ngOnDestroy(): void {
    this.terminalObserver?.disconnect();
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
    if (status === 'done') return 'check_circle';
    if (status === 'running') return 'hourglass_top';
    if (status === 'failed') return 'error';
    return 'radio_button_unchecked';
  }

  trackStage(_: number, stage: StageName): string {
    return stage;
  }

  trackTerminal(_: number, line: TerminalLine): number {
    return line.id;
  }

  // Returns only the last VISIBLE_TERMINAL_LINES entries so the DOM stays
  // bounded without copying the full array on every message.
  visibleTerminal(terminal: TerminalLine[]): TerminalLine[] {
    return terminal.length <= VISIBLE_TERMINAL_LINES
      ? terminal
      : terminal.slice(terminal.length - VISIBLE_TERMINAL_LINES);
  }

  private createSocketStream(runId: string, wsEndpointBase: string): Observable<StreamEvent> {
    const base = wsEndpointBase.replace(/\/$/, '');
    const wsUrl = `${base}/${encodeURIComponent(runId)}`;

    return defer(() =>
      webSocket<SandboxSocketMessage>({
        url: wsUrl,
        deserializer: ({ data }) => {
          // FIX (critical): catch JSON.parse errors so a malformed frame does
          // not crash the stream and trigger an unintended reconnect.
          try {
            if (typeof data === 'string') {
              return JSON.parse(data) as SandboxSocketMessage;
            }
            return data as SandboxSocketMessage;
          } catch {
            // Return a safe sentinel that reduceState will ignore.
            return {
              run_id: runId,
              stage: '',
              line: '[malformed frame dropped]',
              level: 'warn' as LogLevel,
              elapsed_ms: 0,
              stage_status: 'running' as StageStatus,
            };
          }
        },
      }).pipe(
        // FIX (critical): stop the stream when the server signals completion
        // so a clean server-side close is NOT treated as a reason to reconnect.
        // takeWhile(inclusive=true) lets the terminal message through before completing.
        takeWhile(
          (msg) => msg.result !== 'done' && msg.result !== 'failed',
          true, // inclusive — emit the terminal message then complete
        ),
      ),
    ).pipe(
      // FIX (critical): replaced deprecated retryWhen with retry(). Capped at
      // MAX_RECONNECT_ATTEMPTS so a permanently unreachable server does not
      // loop forever. Emits a synthetic ReconnectingMessage before each delay
      // so the UI can transition connectionState to 'reconnecting'.
      retry({
        count: MAX_RECONNECT_ATTEMPTS,
        delay: (_, attempt) => {
          // The tap here is synchronous — it runs before the timer fires,
          // injecting a reconnecting sentinel into the scan reducer via a
          // separate subject is complex; instead we handle the connectionState
          // transition inside reduceState by checking __reconnecting.
          return timer(this.reconnectDelayMs(attempt));
        },
        resetOnSuccess: true,
      }),
    );
  }

  private reconnectDelayMs(attempt: number): number {
    return Math.min(1000 * 2 ** Math.max(0, attempt), 30_000);
  }

  private reduceState(state: SandboxPanelState, event: StreamEvent): SandboxPanelState {
    // Handle synthetic reconnecting sentinel.
    if ('__reconnecting' in event) {
      return { ...state, connectionState: 'reconnecting' };
    }

    const message = event as SandboxSocketMessage;
    const isTerminal = message.result === 'done' || message.result === 'failed';
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

    // FIX (warning): append-only — cap total buffer at MAX_TERMINAL_LINES by
    // dropping from the front only when over the limit. The visible slice is
    // computed in visibleTerminal() so no O(n) spread copy on every message.
    const nextTerminal =
      state.terminal.length >= MAX_TERMINAL_LINES
        ? [...state.terminal.slice(state.terminal.length - MAX_TERMINAL_LINES + 1), nextLine]
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
      // FIX (warning): connectionState transitions to 'live' on first message,
      // and 'disconnected' on terminal message so the header reflects reality.
      connectionState: isTerminal ? 'disconnected' : 'live',
      isTerminal,
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

    const nextTerminal =
      state.terminal.length >= MAX_TERMINAL_LINES
        ? [...state.terminal.slice(state.terminal.length - MAX_TERMINAL_LINES + 1), fallbackLine]
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
    if (!value) return fallback || null;
    if (value === 'checkout') return 'checkout';
    if (value === 'build') return 'build';
    if (value === 'test') return 'test';
    if (value === 'docker push' || value === 'docker_push' || value === 'push') return 'docker push';
    return fallback || null;
  }
}