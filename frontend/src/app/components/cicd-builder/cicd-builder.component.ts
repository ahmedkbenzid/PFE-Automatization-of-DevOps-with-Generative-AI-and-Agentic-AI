import { AsyncPipe, CommonModule, NgFor, NgIf } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  Input,
  OnChanges,
  OnDestroy,
  SimpleChanges,
  ChangeDetectorRef,
  ElementRef,
  ViewChild,
  AfterViewChecked,
} from '@angular/core';
import { BehaviorSubject, Subject, of, timer } from 'rxjs';
import {
  catchError,
  filter,
  switchMap,
  takeUntil,
  tap,
} from 'rxjs/operators';
import {
  ApiService,
  ExecutionLogEntry,
  ExecutionLogsResponse,
  ExecutionResultResponse,
  RunStatusResponse,
} from '../../services/api.service';

interface TerminalLine {
  id: number;
  line: string;
  level: 'info' | 'warn' | 'error';
  stage?: string;
  timestamp: Date;
}

@Component({
  selector: 'app-cicd-builder',
  standalone: true,
  imports: [CommonModule, NgIf, NgFor, AsyncPipe],
  template: `
    <div class="terminal-wrap">

      <!-- Summary bar -->
      <div class="summary-bar" *ngIf="executionResult$ | async as execution">
        <span class="summary-lines">
          {{ (terminalLines$ | async)?.length || 0 }} lines
        </span>
        <span class="summary-sep">·</span>
        <span class="summary-exit">
          exit&nbsp;{{ execution?.act?.exit_code === undefined
            ? (execution?.status === 'running' ? '…' : 'n/a')
            : execution?.act?.exit_code }}
        </span>
        <span class="summary-sep" *ngIf="execution?.message">·</span>
        <span class="summary-msg" *ngIf="execution?.message">{{ execution.message }}</span>

        <span class="summary-spacer"></span>

        <span class="result-badge"
          [class.running]="execution?.status === 'running'"
          [class.success]="execution?.act?.exit_code === 0 || execution?.status === 'completed'"
          [class.failed]="execution?.act?.exit_code !== 0 && execution?.act?.exit_code !== undefined && execution?.status !== 'running'">
          {{ execution?.status === 'running' ? '⏳ Running'
            : (execution?.act?.exit_code === 0 || execution?.status === 'completed') ? '✅ Success'
            : '❌ Failed' }}
        </span>
      </div>

      <!-- Terminal -->
      <div class="terminal" #terminal>
        <div class="terminal-content">
          <div
            *ngFor="let line of terminalLines$ | async; let i = index"
            class="terminal-line"
            [class.error]="line.level === 'error'"
            [class.warn]="line.level === 'warn'"
          >
            <span class="ln">{{ i + 1 }}</span>
            <span *ngIf="line.stage" class="ls">[{{ line.stage }}]</span>
            <span class="lc">{{ line.line }}</span>
          </div>

          <div
            *ngIf="(isRunning$ | async) && ((terminalLines$ | async)?.length || 0) === 0"
            class="terminal-placeholder"
          >
            <span class="blink">█</span>&nbsp;Waiting for output…
          </div>

          <div
            *ngIf="!(isRunning$ | async) && ((terminalLines$ | async)?.length || 0) === 0"
            class="terminal-placeholder muted"
          >
            No log output captured.
          </div>
        </div>
      </div>

    </div>
  `,
  styles: [`
    /* ── Outer wrap — no extra border, merges into parent logs-section ── */
    .terminal-wrap {
      display: flex;
      flex-direction: column;
      width: 100%;
      background: transparent;
    }

    /* ── Summary bar ────────────────────────────────────────────────── */
    .summary-bar {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 16px;
      background: #0b1524;
      border-bottom: 1px solid #1e2d42;
      font-size: 12px;
      font-family: 'Courier New', monospace;
      flex-wrap: wrap;
    }

    .summary-lines,
    .summary-exit { color: #7a9abf; }
    .summary-sep  { color: #2e4057; }
    .summary-msg  { color: #5a7a9a; font-style: italic; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .summary-spacer { flex: 1; }

    .result-badge {
      font-size: 11px;
      font-weight: 700;
      padding: 2px 10px;
      border-radius: 999px;
      border: 1px solid transparent;
      white-space: nowrap;
      background: rgba(142,164,194,0.1);
      color: #c6d3e8;
      border-color: rgba(142,164,194,0.2);
    }

    .result-badge.running {
      background: rgba(13,140,255,0.15);
      color: #72c1ff;
      border-color: rgba(13,140,255,0.3);
    }

    .result-badge.success {
      background: rgba(0,170,0,0.14);
      color: #8cedab;
      border-color: rgba(0,170,0,0.28);
    }

    .result-badge.failed {
      background: rgba(255,68,68,0.14);
      color: #ff9d9d;
      border-color: rgba(255,68,68,0.3);
    }

    /* ── Terminal ───────────────────────────────────────────────────── */
    .terminal {
      flex: 1;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      min-height: 320px;
      max-height: 600px;
    }

    .terminal-content {
      flex: 1;
      overflow-y: auto;
      padding: 12px 16px;
      font-family: 'Courier New', monospace;
      font-size: 12px;
      line-height: 1.6;
      background: #060d18;
    }

    /* ── Log lines ──────────────────────────────────────────────────── */
    .terminal-line {
      display: flex;
      gap: 10px;
      color: #a8c0d8;
      margin-bottom: 1px;
      word-break: break-all;
    }

    .terminal-line.error { color: #ff7070; }
    .terminal-line.warn  { color: #f0a840; }

    .ln {
      color: #2e4a62;
      min-width: 36px;
      text-align: right;
      flex-shrink: 0;
      user-select: none;
    }

    .ls {
      color: #3a8fd4;
      min-width: 56px;
      flex-shrink: 0;
    }

    .lc {
      flex: 1;
      color: #cfe0f4;
    }

    /* ── Placeholder ────────────────────────────────────────────────── */
    .terminal-placeholder {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 40px 24px;
      color: #2e4a62;
      font-style: italic;
      font-size: 13px;
    }

    .terminal-placeholder.muted { color: #1e3048; }

    @keyframes blink {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0; }
    }

    .blink { animation: blink 1s step-end infinite; color: #3a8fd4; }

    /* ── Scrollbar ──────────────────────────────────────────────────── */
    .terminal-content::-webkit-scrollbar        { width: 6px; }
    .terminal-content::-webkit-scrollbar-track  { background: #060d18; }
    .terminal-content::-webkit-scrollbar-thumb  { background: #1e3048; border-radius: 3px; }
    .terminal-content::-webkit-scrollbar-thumb:hover { background: #2e4a62; }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CicdBuilderComponent implements OnChanges, OnDestroy, AfterViewChecked {
  @Input() executionId: string | null = null;
  @ViewChild('terminal') terminalElement?: ElementRef<HTMLDivElement>;

  private readonly destroy$ = new Subject<void>();

  readonly isRunning$            = new BehaviorSubject<boolean>(false);
  readonly runStatus$            = new BehaviorSubject<RunStatusResponse | null>(null);
  readonly terminalLines$        = new BehaviorSubject<TerminalLine[]>([]);
  readonly buildResult$          = new BehaviorSubject<any>(null);
  readonly executionResult$      = new BehaviorSubject<ExecutionResultResponse | null>(null);
  readonly executionStatusLabel$ = new BehaviorSubject<string>('Loading');

  private lineCounter              = 0;
  private polledLineIndex          = 0;
  private polledExecutionLogIndex  = 0;
  private pollComplete             = false;

  constructor(
    private readonly api: ApiService,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['executionId'] && this.executionId) {
      this.initializeExecution();
    }
  }

  ngAfterViewChecked(): void {
    this.scrollTerminalToBottom();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // ─── Initialise ────────────────────────────────────────────────────────────

  private initializeExecution(): void {
    if (!this.executionId) return;

    this.lineCounter             = 0;
    this.polledLineIndex         = 0;
    this.polledExecutionLogIndex = 0;
    this.pollComplete            = false;
    this.terminalLines$.next([]);
    this.runStatus$.next(null);
    this.buildResult$.next(null);
    this.executionResult$.next(null);
    this.executionStatusLabel$.next('Loading');
    this.isRunning$.next(true);

    // Poll orchestrator run status
    timer(0, 1000)
      .pipe(
        filter(() => !!this.executionId && !this.pollComplete),
        switchMap(() =>
          this.api.getStatus(this.executionId!).pipe(
            catchError((err) => { console.error('Run status poll error:', err); return of(null); })
          )
        ),
        filter((s): s is RunStatusResponse => s !== null),
        tap((status) => {
          this.runStatus$.next(status);
          this.isRunning$.next(status.returncode === null);
          if (status.returncode !== null) {
            this.buildResult$.next({ success: status.returncode === 0, returncode: status.returncode });
            this.pollComplete = true;
          }
        }),
        takeUntil(this.destroy$),
      )
      .subscribe();

    // Poll execution-sandbox status
    timer(0, 1000)
      .pipe(
        filter(() => !!this.executionId && !this.pollComplete),
        switchMap(() =>
          this.api.getExecution(this.executionId!).pipe(
            catchError((err) => { console.error('Execution status poll error:', err); return of(null); })
          )
        ),
        filter((r): r is ExecutionResultResponse => r !== null),
        tap((response) => {
          this.executionResult$.next(response);
          this.executionStatusLabel$.next(this.formatExecutionStatus(response));
          const s = String(response.status || '').toLowerCase();
          this.isRunning$.next(s === 'running' || s === 'pending');
          if (s && s !== 'running' && s !== 'pending') {
            this.buildResult$.next({
              success: s === 'completed' || (response.act && response.act.exit_code === 0),
              returncode: response.act ? response.act.exit_code ?? null : null,
            });
            this.pollComplete = true;
          }
        }),
        takeUntil(this.destroy$),
      )
      .subscribe();

    // Poll execution logs
    timer(0, 1000)
      .pipe(
        filter(() => !!this.executionId && !this.pollComplete),
        switchMap(() =>
          this.api.getExecutionLogs(this.executionId!).pipe(
            catchError((err) => { console.error('Execution logs poll error:', err); return of(null); })
          )
        ),
        filter((r): r is ExecutionLogsResponse => r !== null),
        tap((response) => this.handleLogResponse(response)),
        takeUntil(this.destroy$),
      )
      .subscribe();
  }

  // ─── Helpers ───────────────────────────────────────────────────────────────

  private formatExecutionStatus(execution: ExecutionResultResponse | null): string {
    if (!execution) return 'Loading';
    const s = String(execution.status || '').toLowerCase();
    if (s === 'running' || s === 'pending') return 'Running';
    if (s === 'completed' || (execution.act && execution.act.exit_code === 0)) return 'Completed';
    return 'Failed';
  }

  private normalizeExecutionLogLine(entry: ExecutionLogEntry | string): string {
    if (typeof entry === 'string') return entry;
    const line   = typeof entry.line   === 'string' ? entry.line   : '';
    const prefix = typeof entry.stream === 'string' && entry.stream ? `[${entry.stream}] ` : '';
    const stage  = typeof entry.stage  === 'string' && entry.stage  ? `[${entry.stage}] `  : '';
    if (line) return `${prefix}${stage}${line}`.trim();
    const msg = (entry as Record<string, unknown>)['message'];
    return msg !== undefined ? String(msg) : JSON.stringify(entry);
  }

  private handleLogResponse(response: ExecutionLogsResponse): void {
    const allLogs = Array.isArray(response.logs) ? response.logs : [];
    const newLogs = allLogs.slice(this.polledExecutionLogIndex);
    if (!newLogs.length) return;

    const nextLines = [...this.terminalLines$.value];
    for (const entry of newLogs) {
      nextLines.push({
        id:        this.lineCounter++,
        line:      this.normalizeExecutionLogLine(entry as ExecutionLogEntry),
        level:     'info',
        timestamp: new Date(),
      });
    }

    if (nextLines.length > 500) nextLines.splice(0, nextLines.length - 500);

    this.polledExecutionLogIndex = allLogs.length;
    this.terminalLines$.next(nextLines);
    this.cdr.markForCheck();
  }

  private scrollTerminalToBottom(): void {
    if (this.terminalElement) {
      setTimeout(() => {
        const el = this.terminalElement!.nativeElement;
        el.scrollTop = el.scrollHeight;
      });
    }
  }

  stopBuild():  void { this.pollComplete = true; }
  cleanup():    void { this.pollComplete = true; }
}