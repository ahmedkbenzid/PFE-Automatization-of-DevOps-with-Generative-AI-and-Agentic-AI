// history-dashboard.component.ts
import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil } from 'rxjs';
import { HistoryService, Session, HistoryStats, Artifact } from '../../services/history.service';

type FilterStatus = 'all' | 'completed' | 'failed' | 'running';
type ArtifactTab = Artifact['type'];

@Component({
  selector: 'app-history-dashboard',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule],
  templateUrl: './history-dashboard.component.html',
  styleUrls: ['./history-dashboard.component.scss'],
})
export class HistoryDashboardComponent implements OnInit, OnDestroy {
  sessions: Session[] = [];
  stats: HistoryStats | null = null;
  selectedSession: Session | null = null;
  activeArtifactTab: ArtifactTab = 'cicd';
  activeDetailTab: 'artifacts' | 'logs' | 'repairs' = 'artifacts';
  filterStatus: FilterStatus = 'all';
  searchQuery = '';
  loading = true;
  error: string | null = null;
  copiedArtifact: string | null = null;

  private destroy$ = new Subject<void>();

  constructor(private historyService: HistoryService) {}

  ngOnInit(): void {
    this.loadStats();
    this.loadSessions();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadStats(): void {
    this.historyService.getStats()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (stats) => this.stats = stats,
        error: () => {}
      });
  }

  loadSessions(): void {
    this.loading = true;
    this.error = null;
    const status = this.filterStatus === 'all' ? undefined : this.filterStatus;
    this.historyService.getSessions(100, status)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (sessions) => {
          this.sessions = sessions;
          this.loading = false;
          if (sessions.length > 0 && !this.selectedSession) {
            this.selectSession(sessions[0]);
          }
        },
        error: (err) => {
          this.error = 'Failed to load session history.';
          this.loading = false;
        }
      });
  }

  selectSession(session: Session): void {
    this.selectedSession = session;
    this.activeDetailTab = 'artifacts';
    this.activeArtifactTab = this.getFirstArtifactType(session);
  }

  getFirstArtifactType(session: Session): ArtifactTab {
    const order: ArtifactTab[] = ['cicd', 'dockerfile', 'kubernetes', 'terraform'];
    for (const type of order) {
      if (session.artifacts.some(a => a.type === type)) return type;
    }
    return 'cicd';
  }

  getArtifactByType(session: Session, type: ArtifactTab): Artifact | undefined {
    return session.artifacts.find(a => a.type === type);
  }

  getArtifactTypes(session: Session): ArtifactTab[] {
    return [...new Set(session.artifacts.map(a => a.type))];
  }

  get filteredSessions(): Session[] {
    if (!this.searchQuery.trim()) return this.sessions;
    const q = this.searchQuery.toLowerCase();
    return this.sessions.filter(s =>
      s.prompt.toLowerCase().includes(q) ||
      s.agents_used?.some(a => a.toLowerCase().includes(q))
    );
  }

  onFilterChange(): void {
    this.selectedSession = null;
    this.loadSessions();
  }

  deleteSession(sessionId: string, event: Event): void {
    event.stopPropagation();
    if (!confirm('Delete this session?')) return;
    this.historyService.deleteSession(sessionId)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: () => {
          this.sessions = this.sessions.filter(s => s.session_id !== sessionId);
          if (this.selectedSession?.session_id === sessionId) {
            this.selectedSession = this.sessions[0] ?? null;
          }
          this.loadStats();
        }
      });
  }

  copyArtifact(content: string, type: string): void {
    navigator.clipboard.writeText(content).then(() => {
      this.copiedArtifact = type;
      setTimeout(() => this.copiedArtifact = null, 2000);
    });
  }

  formatDuration(seconds: number | null): string {
    if (!seconds) return '—';
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  }

  formatRelative(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  }

  getStatusClass(status: string): string {
    return { completed: 'status-ok', failed: 'status-fail', running: 'status-run' }[status] ?? '';
  }

  getLogClass(level: string): string {
    return { info: 'log-info', warning: 'log-warn', error: 'log-err', success: 'log-ok' }[level] ?? '';
  }

  getValidationClass(status: string): string {
    return { passed: 'val-ok', failed: 'val-fail', skipped: 'val-skip' }[status] ?? 'val-unk';
  }

  artifactIcon(type: string): string {
    return { cicd: '⚙', dockerfile: '🐳', kubernetes: '☸', terraform: '🏗' }[type] ?? '📄';
  }

  agentIcon(agent: string): string {
    const a = agent?.toLowerCase() ?? '';
    if (a.includes('cicd') || a.includes('ci/cd')) return '⚙';
    if (a.includes('docker')) return '🐳';
    if (a.includes('k8s') || a.includes('kube')) return '☸';
    if (a.includes('terraform') || a.includes('iac')) return '🏗';
    if (a.includes('execut')) return '▶';
    if (a.includes('repair')) return '🔧';
    if (a.includes('plan')) return '📋';
    return '🤖';
  }
}