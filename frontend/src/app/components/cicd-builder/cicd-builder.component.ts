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
import { BehaviorSubject, Observable, Subject, of, timer } from 'rxjs';
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
    <div class="cicd-builder-container">
      <!-- Header -->
      <div class="builder-header">
        <div class="header-title">
          <span class="build-icon">📜</span>
          <span>Execution-Sandbox Logs</span>
        </div>
        <div class="header-actions">
          <span class="status-pill" [class.running]="(executionResult$ | async)?.status === 'running'">
            {{ executionStatusLabel$ | async }}
          </span>
        </div>
      </div>

      <!-- Run Summary -->
      <div class="progress-section" *ngIf="executionResult$ | async as execution">
        <div class="progress-info">
          <span class="progress-text">
            {{ (terminalLines$ | async)?.length || 0 }} sandbox log lines captured
          </span>
          <span class="progress-time">
            Exit code: {{ execution?.act?.exit_code === undefined ? (execution?.status === 'running' ? 'running' : 'n/a') : execution?.act?.exit_code }}
          </span>
        </div>
        <div class="progress-message" *ngIf="execution?.message">
          {{ execution.message }}
        </div>
      </div>

      <!-- Terminal Output -->
      <div class="terminal-section">
        <div class="terminal-header">
          <h3>Live Logs</h3>
          <span class="log-count">
            {{ (terminalLines$ | async)?.length || 0 }} lines
          </span>
        </div>

        <div class="terminal" #terminal>
          <div class="terminal-content">
            <div
              *ngFor="let line of terminalLines$ | async; let i = index"
              class="terminal-line"
              [class.error]="line.level === 'error'"
              [class.warn]="line.level === 'warn'"
            >
              <span class="line-number">{{ i + 1 }}</span>
              <span *ngIf="line.stage" class="line-stage">[{{ line.stage }}]</span>
              <span class="line-content">{{ line.line }}</span>
            </div>

            <div
              *ngIf="(isRunning$ | async) && ((terminalLines$ | async)?.length || 0) === 0"
              class="terminal-placeholder"
            >
              Waiting for output...
            </div>
          </div>
        </div>
      </div>

      <!-- Build Result -->
      <div *ngIf="executionResult$ | async as execution" class="result-section" [class.success]="execution?.act?.exit_code === 0 || execution?.status === 'completed'">
        <div class="result-icon">
          {{ execution?.status === 'running' ? '⏳' : ((execution?.act?.exit_code === 0 || execution?.status === 'completed') ? '✅' : '❌') }}
        </div>
        <div class="result-info">
          <h3 class="result-title">
            Sandbox {{ execution?.status === 'running' ? 'In Progress' : ((execution?.act?.exit_code === 0 || execution?.status === 'completed') ? 'Successful' : 'Failed') }}
          </h3>
          <p class="result-details">
            {{ (terminalLines$ | async)?.length || 0 }} sandbox log lines captured
          </p>
          <p class="result-code">
            Exit code: {{ execution?.act?.exit_code === undefined ? (execution?.status === 'running' ? 'running' : 'n/a') : execution?.act?.exit_code }}
          </p>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .cicd-builder-container {
      display: flex;
      flex-direction: column;
      gap: 16px;
      padding: 20px;
      background: var(--bg-elevated, #1e1e1e);
      border-radius: 12px;
      border: 1px solid var(--border-color, #333);
      max-height: 800px;
      overflow-y: auto;
    }

    .builder-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border-color, #333);
    }

    .header-title {
      font-size: 18px;
      font-weight: 600;
      color: var(--text-primary, #fff);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .build-icon {
      font-size: 24px;
    }

    .header-actions {
      display: flex;
      gap: 8px;
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      padding: 6px 12px;
      border-radius: 999px;
      background: rgba(122, 162, 255, 0.12);
      color: #8ab4ff;
      border: 1px solid rgba(122, 162, 255, 0.25);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .status-pill.running {
      background: rgba(13, 140, 255, 0.15);
      color: #72c1ff;
      border-color: rgba(13, 140, 255, 0.35);
      box-shadow: 0 0 12px rgba(13, 140, 255, 0.12);
    }

    .btn-stop,
    .btn-cleanup {
      padding: 8px 16px;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 500;
      font-size: 13px;
      transition: all 200ms ease;
    }

    .btn-stop {
      background: var(--danger-color, #ff4444);
      color: white;
    }

    .btn-stop:hover {
      background: var(--danger-hover, #cc0000);
      transform: translateY(-2px);
    }

    .btn-cleanup {
      background: var(--bg-base, #0d0d0d);
      color: var(--text-secondary, #999);
      border: 1px solid var(--border-color, #333);
    }

    .btn-cleanup:hover {
      background: var(--bg-hover, #1a1a1a);
      color: var(--text-primary, #fff);
    }

    .progress-section {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .progress-bar {
      height: 6px;
      background: var(--bg-base, #0d0d0d);
      border-radius: 3px;
      overflow: hidden;
      border: 1px solid var(--border-color, #333);
    }

    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, #0d8cff, #00d4ff);
      transition: width 300ms ease;
    }

    .progress-info {
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      color: var(--text-secondary, #999);
    }

    .progress-message {
      font-size: 12px;
      color: var(--text-tertiary, #666);
      line-height: 1.5;
    }

    .stages-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 12px;
    }

    .stage-card {
      padding: 12px;
      border: 2px solid var(--border-color, #333);
      border-radius: 8px;
      background: var(--bg-base, #0d0d0d);
      transition: all 200ms ease;
      cursor: default;
    }

    .stage-card.running {
      border-color: var(--accent-color, #0d8cff);
      background: rgba(13, 140, 255, 0.05);
      box-shadow: 0 0 12px rgba(13, 140, 255, 0.2);
    }

    .stage-card.completed {
      border-color: #00aa00;
      background: rgba(0, 170, 0, 0.05);
    }

    .stage-card.failed {
      border-color: #ff4444;
      background: rgba(255, 68, 68, 0.05);
    }

    .stage-header {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      margin-bottom: 8px;
    }

    .stage-status-icon {
      font-size: 18px;
      min-width: 20px;
      text-align: center;
    }

    .stage-info {
      flex: 1;
      min-width: 0;
    }

    .stage-name {
      margin: 0;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-primary, #fff);
      word-break: break-word;
    }

    .stage-status {
      margin: 2px 0 0 0;
      font-size: 11px;
      color: var(--text-secondary, #999);
      text-transform: uppercase;
    }

    .stage-duration,
    .log-count {
      font-size: 11px;
      color: var(--text-secondary, #999);
      font-family: monospace;
    }

    .stage-duration {
      margin-bottom: 4px;
    }

    .stage-error {
      font-size: 11px;
      color: #ff4444;
      margin-top: 4px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .terminal-section {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .terminal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 12px;
      background: var(--bg-base, #0d0d0d);
      border-radius: 6px 6px 0 0;
      border-bottom: 1px solid var(--border-color, #333);
    }

    .terminal-header h3 {
      margin: 0;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-primary, #fff);
    }

    .log-count {
      padding: 2px 6px;
      background: var(--accent-bg, #1a3a4a);
      border-radius: 4px;
    }

    .terminal {
      background: var(--bg-base, #0d0d0d);
      border: 1px solid var(--border-color, #333);
      border-radius: 0 0 6px 6px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      max-height: 300px;
    }

    .terminal-content {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
      font-family: 'Courier New', monospace;
      font-size: 12px;
      line-height: 1.5;
    }

    .terminal-line {
      display: flex;
      gap: 8px;
      color: var(--text-secondary, #999);
      margin-bottom: 2px;
      word-break: break-all;
    }

    .terminal-line.error {
      color: #ff6b6b;
    }

    .terminal-line.warn {
      color: #ffa500;
    }

    .line-number {
      color: var(--text-tertiary, #666);
      min-width: 40px;
      text-align: right;
      flex-shrink: 0;
    }

    .line-stage {
      color: var(--accent-color, #0d8cff);
      min-width: 60px;
      flex-shrink: 0;
    }

    .line-content {
      flex: 1;
      color: var(--text-primary, #fff);
    }

    .terminal-placeholder {
      text-align: center;
      color: var(--text-tertiary, #666);
      padding: 24px;
      font-style: italic;
    }

    .result-section {
      padding: 16px;
      border-radius: 8px;
      background: var(--bg-base, #0d0d0d);
      border: 2px solid var(--border-color, #333);
      display: flex;
      gap: 12px;
      align-items: center;
    }

    .result-section.success {
      border-color: #00aa00;
      background: rgba(0, 170, 0, 0.05);
    }

    .result-icon {
      font-size: 32px;
    }

    .result-info {
      flex: 1;
    }

    .result-title {
      margin: 0 0 4px 0;
      font-size: 16px;
      font-weight: 600;
      color: var(--text-primary, #fff);
    }

    .result-details,
    .result-code {
      margin: 2px 0;
      font-size: 13px;
      color: var(--text-secondary, #999);
    }

    ::-webkit-scrollbar {
      width: 8px;
      height: 8px;
    }

    ::-webkit-scrollbar-track {
      background: var(--bg-base, #0d0d0d);
    }

    ::-webkit-scrollbar-thumb {
      background: var(--border-color, #333);
      border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb:hover {
      background: var(--text-secondary, #999);
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CicdBuilderComponent implements OnChanges, OnDestroy, AfterViewChecked {
  @Input() executionId: string | null = null;
  @ViewChild('terminal') terminalElement?: ElementRef<HTMLDivElement>;

  private readonly destroy$ = new Subject<void>();

  readonly isRunning$ = new BehaviorSubject<boolean>(false);
  readonly runStatus$ = new BehaviorSubject<RunStatusResponse | null>(null);
  readonly terminalLines$ = new BehaviorSubject<TerminalLine[]>([]);
  readonly buildResult$ = new BehaviorSubject<any>(null);
  readonly executionResult$ = new BehaviorSubject<ExecutionResultResponse | null>(null);
  readonly executionStatusLabel$ = new BehaviorSubject<string>('Loading');

  private lineCounter = 0;
  private polledLineIndex = 0;
  private polledExecutionLogIndex = 0;
  private pollComplete = false;

  constructor(private readonly api: ApiService, private cdr: ChangeDetectorRef) {}

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

  private initializeExecution(): void {
    if (!this.executionId) return;

    this.lineCounter = 0;
    this.polledLineIndex = 0;
    this.polledExecutionLogIndex = 0;
    this.pollComplete = false;
    this.terminalLines$.next([]);
    this.runStatus$.next(null);
    this.buildResult$.next(null);
    this.executionResult$.next(null);
    this.executionStatusLabel$.next('Loading');

    this.isRunning$.next(true);

    // Poll orchestrator run status (keeps quick UI feedback)
    timer(0, 1000)
      .pipe(
        filter(() => !!this.executionId && !this.pollComplete),
        switchMap(() =>
          this.api.getStatus(this.executionId!).pipe(
            catchError((error) => {
              console.error('Run status poll error:', error);
              return of(null);
            })
          )
        ),
        filter((status): status is RunStatusResponse => status !== null),
        tap((status) => {
          this.runStatus$.next(status);
          this.isRunning$.next(status.returncode === null);

          if (status.returncode !== null) {
            this.buildResult$.next({
              success: status.returncode === 0,
              returncode: status.returncode,
            });
            this.pollComplete = true;
          }
        }),
        takeUntil(this.destroy$)
      )
      .subscribe();

    // Poll execution-sandbox status
    timer(0, 1000)
      .pipe(
        filter(() => !!this.executionId && !this.pollComplete),
        switchMap(() =>
          this.api.getExecution(this.executionId!).pipe(
            catchError((error) => {
              console.error('Execution status poll error:', error);
              return of(null);
            })
          )
        ),
        filter((response): response is ExecutionResultResponse => response !== null),
        tap((response) => {
          this.executionResult$.next(response);
          this.executionStatusLabel$.next(this.formatExecutionStatus(response));

          const status = String(response.status || '').toLowerCase();
          this.isRunning$.next(status === 'running' || status === 'pending');
          if (status && status !== 'running' && status !== 'pending') {
            this.buildResult$.next({
              success: status === 'completed' || (response.act && response.act.exit_code === 0),
              returncode: response.act ? response.act.exit_code ?? null : null,
            });
            this.pollComplete = true;
          }
        }),
        takeUntil(this.destroy$)
      )
      .subscribe();

    // Poll execution logs (JSONL emitted by the sandbox)
    timer(0, 1000)
      .pipe(
        filter(() => !!this.executionId && !this.pollComplete),
        switchMap(() =>
          this.api.getExecutionLogs(this.executionId!).pipe(
            catchError((error) => {
              console.error('Execution logs poll error:', error);
              return of(null);
            })
          )
        ),
        filter((response): response is ExecutionLogsResponse => response !== null),
        tap((response) => this.handleLogResponse(response)),
        takeUntil(this.destroy$)
      )
      .subscribe();
  }

  private formatExecutionStatus(execution: ExecutionResultResponse | null): string {
    if (!execution) return 'Loading';
    const status = String(execution.status || '').toLowerCase();
    if (status === 'running' || status === 'pending') return 'Running';
    if (status === 'completed' || (execution.act && execution.act.exit_code === 0)) return 'Completed';
    return 'Failed';
  }

  private normalizeExecutionLogLine(entry: ExecutionLogEntry | string): string {
    if (typeof entry === 'string') return entry;
    const line = typeof entry.line === 'string' ? entry.line : '';
    const prefix = typeof entry.stream === 'string' && entry.stream ? `[${entry.stream}] ` : '';
    const stage = typeof entry.stage === 'string' && entry.stage ? `[${entry.stage}] ` : '';
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
      const newLine: TerminalLine = {
        id: this.lineCounter++,
        line: this.normalizeExecutionLogLine(entry as ExecutionLogEntry),
        level: 'info',
        timestamp: new Date(),
      };
      nextLines.push(newLine);
    }

    if (nextLines.length > 500) nextLines.splice(0, nextLines.length - 500);

    this.polledExecutionLogIndex = allLogs.length;
    this.terminalLines$.next(nextLines);
    this.cdr.markForCheck();
  }

  private scrollTerminalToBottom(): void {
    if (this.terminalElement) {
      setTimeout(() => {
        const content = this.terminalElement!.nativeElement;
        content.scrollTop = content.scrollHeight;
      });
    }
  }

  stopBuild(): void {
    this.pollComplete = true;
  }

  cleanup(): void {
    this.pollComplete = true;
  }
}
