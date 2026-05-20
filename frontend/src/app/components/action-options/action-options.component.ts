import { Component, Input, Output, EventEmitter, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ArtifactsService } from '../../services/artifacts.service';

export interface EditedArtifacts {
  yaml: string | null;
  dockerfile: string | null;
  terraform: {
    main_tf: string;
    variables_tf: string;
    outputs_tf: string;
    providers_tf: string;
  };
  kubernetes: {
    namespace_yaml: string;
    configmap_yaml: string;
    secret_yaml: string;
    deployment_yaml: string;
    service_yaml: string;
    ingress_yaml: string;
    hpa_yaml: string;
  };
  metadata: any;
}

export interface ActionOptionsInput {
  repoPathAvailable: boolean;
  githubUrl?: string;
  repoPath?: string;
  editedArtifacts: EditedArtifacts;
  feedbackResult?: any;
}

type TopTab = 'cicd' | 'dockerfile' | 'terraform' | 'kubernetes';
type TerraformSubTab = 'main_tf' | 'variables_tf' | 'outputs_tf' | 'providers_tf';
type KubernetesSubTab = 'deployment_yaml' | 'service_yaml' | 'namespace_yaml' |
                        'configmap_yaml' | 'secret_yaml' | 'ingress_yaml' | 'hpa_yaml';

interface TabDef {
  id: TopTab;
  label: string;
  icon: string;
  hasContent: (a: EditedArtifacts) => boolean;
}

@Component({
  selector: 'app-action-options',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="editor-shell">

      <!-- ── Top tab bar ── -->
      <div class="tab-bar">
        <button
          *ngFor="let tab of topTabs"
          class="tab-btn"
          [class.active]="activeTab === tab.id"
          [class.empty]="!tab.hasContent(draft)"
          (click)="activeTab = tab.id"
          [title]="tab.label"
        >
          <span class="h-4 w-4 shrink-0 [&>svg]:h-4 [&>svg]:w-4 [&>svg]:stroke-current" [innerHTML]="tab.icon"></span>
          <span class="tab-label">{{ tab.label }}</span>
          <span class="tab-dot" *ngIf="isDirty(tab.id)"></span>
        </button>

        <div class="tab-spacer"></div>

        <!-- Action buttons live in the tab bar -->
        <div class="action-strip">
          <button class="act-btn secondary" (click)="onReset()" title="Revert all edits">
            Reset
          </button>
          <button
            class="act-btn secondary"
            (click)="onDownloadOnly()"
            [disabled]="isLoading"
          >
            <span *ngIf="!isLoading">↓ Download</span>
            <span *ngIf="isLoading">…</span>
          </button>
          <button
            class="act-btn primary"
            (click)="onApplyToRepository()"
            [disabled]="isLoading || !input.repoPathAvailable"
            [title]="applyButtonHelp"
          >
            <span *ngIf="!isLoading">✓ Apply to Repo</span>
            <span *ngIf="isLoading"><span class="spin"></span> Working…</span>
          </button>
          <button class="act-btn danger" (click)="onReject()" [disabled]="isLoading">
            ✕ Reject
          </button>
        </div>
      </div>

      <!-- ── Status banner ── -->
      <div class="banner success" *ngIf="successMessage">{{ successMessage }}</div>
      <div class="banner error"   *ngIf="errorMessage">{{ errorMessage }}</div>

      <!-- ── Editor area ── -->
      <div class="editor-area">

        <!-- CI/CD YAML -->
        <div class="pane" *ngIf="activeTab === 'cicd'">
          <div class="pane-header">
            <span class="pane-title">GitHub Actions Workflow</span>
            <span class="pane-file">.github/workflows/ci.yml</span>
            <span class="pane-hint">YAML</span>
          </div>
          <textarea
            class="code-editor"
            [(ngModel)]="draft.yaml"
            placeholder="# No CI/CD workflow generated yet"
            spellcheck="false"
            autocomplete="off"
          ></textarea>
        </div>

        <!-- Dockerfile -->
        <div class="pane" *ngIf="activeTab === 'dockerfile'">
          <div class="pane-header">
            <span class="pane-title">Dockerfile</span>
            <span class="pane-file">Dockerfile</span>
            <span class="pane-hint">Docker</span>
          </div>
          <textarea
            class="code-editor"
            [(ngModel)]="draft.dockerfile"
            placeholder="# No Dockerfile generated yet"
            spellcheck="false"
            autocomplete="off"
          ></textarea>
        </div>

        <!-- Terraform -->
        <div class="pane" *ngIf="activeTab === 'terraform'">
          <div class="sub-tab-bar">
            <button
              *ngFor="let s of terraformSubTabs"
              class="sub-tab-btn"
              [class.active]="activeTfTab === s.id"
              [class.empty]="!draft.terraform[s.id]"
              (click)="activeTfTab = s.id"
            >{{ s.label }}</button>
          </div>
          <div class="pane-header">
            <span class="pane-title">Terraform — {{ activeTfTab }}</span>
            <span class="pane-file">{{ activeTfTab }}</span>
            <span class="pane-hint">HCL</span>
          </div>
          <textarea
            class="code-editor"
            [(ngModel)]="draft.terraform[activeTfTab]"
            [placeholder]="'# No ' + activeTfTab + ' generated yet'"
            spellcheck="false"
            autocomplete="off"
          ></textarea>
        </div>

        <!-- Kubernetes -->
        <div class="pane" *ngIf="activeTab === 'kubernetes'">
          <div class="sub-tab-bar">
            <button
              *ngFor="let s of kubernetesSubTabs"
              class="sub-tab-btn"
              [class.active]="activeK8sTab === s.id"
              [class.empty]="!draft.kubernetes[s.id]"
              (click)="activeK8sTab = s.id"
            >{{ s.label }}</button>
          </div>
          <div class="pane-header">
            <span class="pane-title">Kubernetes — {{ activeK8sTab }}</span>
            <span class="pane-file">{{ activeK8sTab }}</span>
            <span class="pane-hint">YAML</span>
          </div>
          <textarea
            class="code-editor"
            [(ngModel)]="draft.kubernetes[activeK8sTab]"
            [placeholder]="'# No ' + activeK8sTab + ' generated yet'"
            spellcheck="false"
            autocomplete="off"
          ></textarea>
        </div>

      </div>
    </div>
  `,
  styles: [`
    /* ── Shell ─────────────────────────────────────────────────── */
    .editor-shell {
      display: flex;
      flex-direction: column;
      height: 100%;
      min-height: 520px;
      background: #060d18;
      border-radius: 0 0 16px 16px;
      overflow: hidden;
    }

    /* ── Top tab bar ────────────────────────────────────────────── */
    .tab-bar {
      display: flex;
      align-items: center;
      gap: 2px;
      padding: 0 12px;
      background: #0a1422;
      border-bottom: 1px solid #1a2a3d;
      min-height: 44px;
      flex-shrink: 0;
      overflow-x: auto;
    }

    .tab-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 10px 14px;
      font-size: 12px;
      font-weight: 600;
      color: #3a5a7a;
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      cursor: pointer;
      transition: color 120ms ease, border-color 120ms ease;
      white-space: nowrap;
      position: relative;

      &:hover       { color: #7aaacf; }
      &.active      { color: #c8dff4; border-bottom-color: #4f8ef7; }
      &.empty       { opacity: 0.4; }
    }

    .tab-icon  { font-size: 14px; }
    .tab-label { letter-spacing: 0.02em; }

    .tab-dot {
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: #f0a840;
      position: absolute;
      top: 8px;
      right: 6px;
    }

    .tab-spacer { flex: 1; }

    /* ── Action strip ───────────────────────────────────────────── */
    .action-strip {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 0;
      flex-shrink: 0;
    }

    .act-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      transition: opacity 120ms ease, transform 120ms ease;
      border: 1px solid transparent;
      white-space: nowrap;

      &:disabled { opacity: 0.35; cursor: not-allowed; }
      &:not(:disabled):hover { opacity: 0.88; transform: translateY(-1px); }
      &:not(:disabled):active { transform: translateY(0); }
    }

    .act-btn.secondary {
      background: #0e1e30;
      color: #7aaacf;
      border-color: #1e3050;
    }

    .act-btn.primary {
      background: linear-gradient(135deg, #2d6df0, #4f8ef7);
      color: #fff;
    }

    .act-btn.danger {
      background: rgba(248,113,113,0.1);
      color: #f87171;
      border-color: rgba(248,113,113,0.25);
    }

    .spin {
      display: inline-block;
      width: 12px;
      height: 12px;
      border: 2px solid rgba(255,255,255,0.25);
      border-top-color: #fff;
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
    }

    /* ── Status banners ─────────────────────────────────────────── */
    .banner {
      padding: 10px 16px;
      font-size: 12px;
      font-weight: 600;
      flex-shrink: 0;
    }

    .banner.success {
      background: rgba(0,170,0,0.1);
      color: #8cedab;
      border-bottom: 1px solid rgba(0,170,0,0.2);
    }

    .banner.error {
      background: rgba(248,113,113,0.09);
      color: #f87171;
      border-bottom: 1px solid rgba(248,113,113,0.2);
    }

    /* ── Editor area ────────────────────────────────────────────── */
    .editor-area {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    .pane {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    /* ── Sub-tab bar (Terraform / Kubernetes) ───────────────────── */
    .sub-tab-bar {
      display: flex;
      gap: 2px;
      padding: 6px 12px 0;
      background: #080f1e;
      border-bottom: 1px solid #131f30;
      flex-shrink: 0;
      overflow-x: auto;
    }

    .sub-tab-btn {
      padding: 6px 12px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.04em;
      color: #2d4a62;
      background: transparent;
      border: 1px solid transparent;
      border-radius: 6px 6px 0 0;
      cursor: pointer;
      transition: color 100ms ease, background 100ms ease;
      white-space: nowrap;

      &:hover  { color: #7aaacf; background: rgba(79,142,247,0.06); }
      &.active { color: #c8dff4; background: #060d18; border-color: #1a2a3d #1a2a3d transparent; }
      &.empty  { opacity: 0.35; }
    }

    /* ── Pane header ────────────────────────────────────────────── */
    .pane-header {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 16px;
      background: #080f1e;
      border-bottom: 1px solid #0e1a28;
      flex-shrink: 0;
    }

    .pane-title {
      font-size: 12px;
      font-weight: 700;
      color: #4a6a8a;
      flex: 1;
    }

    .pane-file {
      font-size: 11px;
      font-family: 'Courier New', monospace;
      color: #2d4a62;
      background: #060d18;
      border: 1px solid #1a2a3d;
      padding: 2px 8px;
      border-radius: 4px;
    }

    .pane-hint {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #4f8ef7;
      background: rgba(79,142,247,0.1);
      border: 1px solid rgba(79,142,247,0.2);
      padding: 2px 7px;
      border-radius: 4px;
    }

    /* ── Code textarea ──────────────────────────────────────────── */
    .code-editor {
      flex: 1;
      width: 100%;
      box-sizing: border-box;
      background: #060d18;
      border: none;
      resize: none;
      padding: 16px 20px;
      font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Courier New', monospace;
      font-size: 12.5px;
      line-height: 1.75;
      color: #c8dff4;
      outline: none;
      tab-size: 2;
      -moz-tab-size: 2;
      min-height: 360px;

      &::placeholder { color: #1e3050; }

      &:focus {
        background: #07101d;
        box-shadow: inset 0 0 0 1px rgba(79,142,247,0.15);
      }

      /* Scrollbar */
      &::-webkit-scrollbar        { width: 6px; height: 6px; }
      &::-webkit-scrollbar-track  { background: #060d18; }
      &::-webkit-scrollbar-thumb  { background: #1a2a3d; border-radius: 3px; }
      &::-webkit-scrollbar-thumb:hover { background: #2a3d55; }
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    /* ── Responsive ─────────────────────────────────────────────── */
    @media (max-width: 640px) {
      .tab-label   { display: none; }
      .act-btn     { padding: 6px 10px; font-size: 11px; }
      .action-strip { gap: 4px; }
    }
  `],
})
export class ActionOptionsComponent implements OnInit, OnChanges {
  @Input() input!: ActionOptionsInput;
  @Output() accepted = new EventEmitter<{ artifacts: EditedArtifacts; applied: boolean }>();
  @Output() rejected = new EventEmitter<void>();

  isLoading     = false;
  errorMessage: string | null  = null;
  successMessage: string | null = null;

  activeTab: TopTab          = 'cicd';
  activeTfTab: TerraformSubTab  = 'main_tf';
  activeK8sTab: KubernetesSubTab = 'deployment_yaml';

  /** Live-edited copy — this is the source of truth for all actions */
  draft: EditedArtifacts = this.emptyDraft();

  /** Snapshot taken when input arrives, used for dirty detection and reset */
  private snapshot: EditedArtifacts = this.emptyDraft();

readonly topTabs: TabDef[] = [
  {
    id: 'cicd',
    label: 'CI/CD',
    icon: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>`,
    hasContent: (a) => !!a.yaml,
  },
  {
    id: 'dockerfile',
    label: 'Dockerfile',
    icon: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/><line x1="12" y1="12" x2="12" y2="16"/><line x1="10" y1="14" x2="14" y2="14"/></svg>`,
    hasContent: (a) => !!a.dockerfile,
  },
  {
    id: 'terraform',
    label: 'Terraform',
    icon: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7"/><polyline points="2 17 12 22 22 17"/><line x1="2" y1="12" x2="12" y2="17"/><line x1="22" y1="12" x2="12" y2="17"/></svg>`,
    hasContent: (a) => Object.values(a.terraform).some(Boolean),
  },
  {
    id: 'kubernetes',
    label: 'Kubernetes',
    icon: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><circle cx="12" cy="12" r="3"/></svg>`,
    hasContent: (a) => Object.values(a.kubernetes).some(Boolean),
  },
];

  readonly terraformSubTabs: { id: TerraformSubTab; label: string }[] = [
    { id: 'main_tf',       label: 'main.tf' },
    { id: 'variables_tf',  label: 'variables.tf' },
    { id: 'outputs_tf',    label: 'outputs.tf' },
    { id: 'providers_tf',  label: 'providers.tf' },
  ];

  readonly kubernetesSubTabs: { id: KubernetesSubTab; label: string }[] = [
    { id: 'deployment_yaml',  label: 'deployment' },
    { id: 'service_yaml',     label: 'service' },
    { id: 'namespace_yaml',   label: 'namespace' },
    { id: 'configmap_yaml',   label: 'configmap' },
    { id: 'secret_yaml',      label: 'secret' },
    { id: 'ingress_yaml',     label: 'ingress' },
    { id: 'hpa_yaml',         label: 'hpa' },
  ];

  constructor(private artifactsService: ArtifactsService) {}

  ngOnInit(): void {
    this.syncFromInput();
    this.autoSelectTab();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['input'] && !changes['input'].firstChange) {
      this.syncFromInput();
      this.autoSelectTab();
    }
  }

  // ── Dirty detection ──────────────────────────────────────────────────────

  isDirty(tab: TopTab): boolean {
    switch (tab) {
      case 'cicd':
        return this.draft.yaml !== this.snapshot.yaml;
      case 'dockerfile':
        return this.draft.dockerfile !== this.snapshot.dockerfile;
      case 'terraform':
        return JSON.stringify(this.draft.terraform) !== JSON.stringify(this.snapshot.terraform);
      case 'kubernetes':
        return JSON.stringify(this.draft.kubernetes) !== JSON.stringify(this.snapshot.kubernetes);
    }
  }

  // ── Reset ────────────────────────────────────────────────────────────────

  onReset(): void {
    this.draft    = this.deepClone(this.snapshot);
    this.errorMessage   = null;
    this.successMessage = null;
  }

  // ── Apply ────────────────────────────────────────────────────────────────

  async onApplyToRepository(): Promise<void> {
    if (!this.input.repoPath) {
      this.errorMessage = 'No valid repository path available. Clone the repository locally first.';
      return;
    }

    this.isLoading      = true;
    this.errorMessage   = null;
    this.successMessage = null;

    try {
      const result = await this.artifactsService
        .applyArtifactsToRepository(this.input.repoPath, this.draft)
        .toPromise();

      if (result?.success) {
        this.successMessage = `Artifacts applied — ${result.artifacts_written?.length ?? 0} file(s) written`;
        this.snapshot = this.deepClone(this.draft);       // reset dirty flags
        this.accepted.emit({ artifacts: this.draft, applied: true });
      } else {
        this.errorMessage = 'Failed to apply artifacts: ' + (result?.error ?? 'Unknown error');
      }
    } catch (error) {
      this.errorMessage = `Error applying artifacts: ${error instanceof Error ? error.message : 'Unknown error'}`;
    } finally {
      this.isLoading = false;
    }
  }

  // ── Download ─────────────────────────────────────────────────────────────

  async onDownloadOnly(): Promise<void> {
    this.isLoading      = true;
    this.errorMessage   = null;
    this.successMessage = null;

    try {
      const result = await this.artifactsService
        .downloadArtifacts(this.draft)
        .toPromise();

      if (result?.success) {
        this.successMessage = 'Artifacts prepared for download';
        this.accepted.emit({ artifacts: this.draft, applied: false });
        if (result.download_url) window.open(result.download_url, '_blank');
      } else {
        this.errorMessage = 'Failed to prepare download: ' + (result?.error ?? 'Unknown error');
      }
    } catch (error) {
      this.errorMessage = `Error preparing download: ${error instanceof Error ? error.message : 'Unknown error'}`;
    } finally {
      this.isLoading = false;
    }
  }

  // ── Reject ───────────────────────────────────────────────────────────────

  async onReject(): Promise<void> {
    this.isLoading      = true;
    this.errorMessage   = null;
    this.successMessage = null;

    try {
      await this.artifactsService.rejectArtifacts(this.draft).toPromise();
      this.successMessage = 'Artifacts rejected — PR creation skipped.';
      this.rejected.emit();
    } catch (error) {
      this.errorMessage = `Error rejecting: ${error instanceof Error ? error.message : 'Unknown error'}`;
    } finally {
      this.isLoading = false;
    }
  }

  getCurrentDraft(): EditedArtifacts {
    return this.deepClone(this.draft);
  }

  // ── Helpers ──────────────────────────────────────────────────────────────

  get applyButtonHelp(): string {
    return this.input.repoPathAvailable
      ? 'Save artifacts to your repository'
      : 'Clone the repository locally first to apply artifacts';
  }

  private syncFromInput(): void {
    if (!this.input?.editedArtifacts) return;
    this.snapshot = this.deepClone(this.input.editedArtifacts);
    this.draft    = this.deepClone(this.input.editedArtifacts);
  }

  private autoSelectTab(): void {
    const a = this.draft;
    if (a.yaml)                                              { this.activeTab = 'cicd';       return; }
    if (a.dockerfile)                                        { this.activeTab = 'dockerfile'; return; }
    if (Object.values(a.terraform).some(Boolean))            { this.activeTab = 'terraform';  return; }
    if (Object.values(a.kubernetes).some(Boolean))           { this.activeTab = 'kubernetes'; return; }
  }

  private emptyDraft(): EditedArtifacts {
    return {
      yaml: null,
      dockerfile: null,
      terraform:  { main_tf: '', variables_tf: '', outputs_tf: '', providers_tf: '' },
      kubernetes: {
        namespace_yaml: '', configmap_yaml: '', secret_yaml: '',
        deployment_yaml: '', service_yaml: '', ingress_yaml: '', hpa_yaml: '',
      },
      metadata: {},
    };
  }

  private deepClone<T>(obj: T): T {
    return JSON.parse(JSON.stringify(obj));
  }
}