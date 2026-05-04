import { AsyncPipe, CommonModule, NgFor, NgIf } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Output,
  ChangeDetectorRef,
  OnInit,
} from '@angular/core';
import { FormBuilder, FormControl, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { BehaviorSubject, debounceTime, distinctUntilChanged } from 'rxjs';

interface SecretField {
  key: string;
  label: string;
  type: 'password' | 'text';
  placeholder: string;
  description?: string;
}

interface SecretGroup {
  type: string;
  icon: string;
  label: string;
  fields: SecretField[];
  expanded: boolean;
}

@Component({
  selector: 'app-secrets-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule, NgIf, NgFor, AsyncPipe],
  template: `
    <div class="secrets-container">
      <div class="secrets-header">
        <h2 class="secrets-title">
          <span class="icon">🔐</span> Secrets & Credentials
        </h2>
        <p class="secrets-description">
          Add credentials for Docker registries, GitHub, cloud providers, and more.
          Secrets are stored securely and only sent to the execution sandbox.
        </p>
      </div>

      <div class="secrets-groups">
        <div *ngFor="let group of secretGroups" class="secret-group">
          <button
            type="button"
            class="group-header"
            (click)="toggleGroup(group.type)"
            [class.expanded]="group.expanded"
          >
            <span class="group-icon">
              <img *ngIf="group.icon.startsWith('assets/')" [src]="group.icon" [alt]="group.label" class="group-icon-img" />
              <ng-container *ngIf="!group.icon.startsWith('assets/')">{{ group.icon }}</ng-container>
            </span>
            <span class="group-label">{{ group.label }}</span>
            <span class="group-toggle">{{ group.expanded ? '▼' : '▶' }}</span>
          </button>

          <div *ngIf="group.expanded" class="group-fields">
            <div *ngFor="let field of group.fields" class="field-wrapper">
              <label [for]="field.key" class="field-label">
                {{ field.label }}
              </label>
              <input
                [id]="field.key"
                [type]="field.type"
                [formControl]="getFieldControl(field.key)!"
                class="field-input"
                [placeholder]="field.placeholder"
                [attr.aria-label]="field.label"
              />
              <p *ngIf="field.description" class="field-description">
                {{ field.description }}
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- Custom Secret Input -->
      <div class="custom-secret-section">
        <h3 class="custom-title">Add Custom Secret</h3>
        <div class="custom-fields">
          <div class="field-wrapper">
            <label for="custom-key" class="field-label">Key Name</label>
            <input
              id="custom-key"
              type="text"
              [(ngModel)]="customSecretKey"
              placeholder="e.g., MY_API_KEY"
              class="field-input"
              pattern="^[A-Za-z_][A-Za-z0-9_]*$"
              aria-label="Custom secret key"
            />
          </div>
          <div class="field-wrapper">
            <label for="custom-value" class="field-label">Value</label>
            <input
              id="custom-value"
              type="password"
              [(ngModel)]="customSecretValue"
              placeholder="Enter the secret value"
              class="field-input"
              aria-label="Custom secret value"
            />
          </div>
          <button
            type="button"
            class="btn-add-custom"
            (click)="addCustomSecret()"
            [disabled]="!customSecretKey || !customSecretValue"
          >
            + Add Secret
          </button>
        </div>
      </div>

      <!-- Added Secrets Summary -->
      <div class="secrets-summary" *ngIf="(activeSecrets$ | async) as secrets">
        <div *ngIf="Object.keys(secrets).length > 0" class="summary-content">
          <h3 class="summary-title">Active Secrets ({{ Object.keys(secrets).length }})</h3>
          <div class="secrets-list">
            <div *ngFor="let key of Object.keys(secrets)" class="secret-item">
              <span class="secret-key">{{ key }}</span>
              <span class="secret-value-masked">{{ maskValue(secrets[key]) }}</span>
              <button
                type="button"
                class="btn-remove"
                (click)="removeSecret(key)"
                [attr.aria-label]="'Remove ' + key"
                title="Remove this secret"
              >
                ✕
              </button>
            </div>
          </div>
        </div>
        <div *ngIf="Object.keys(secrets).length === 0" class="summary-empty">
          No secrets configured yet
        </div>
      </div>

      <!-- Security Notice -->
      <div class="security-notice">
        <p>
          <strong>🔒 Security Notice:</strong> Secrets are only stored in your browser session
          and sent directly to the execution sandbox. They are never persisted or logged.
        </p>
      </div>
    </div>
  `,
  styles: [`
    .secrets-container {
      max-width: 900px;
      margin: 0 auto;
      padding: 24px;
      background: var(--bg-elevated, #1e1e1e);
      border-radius: 12px;
      border: 1px solid var(--border-color, #333);
    }
    .group-icon-img {
      width: 22px;
      height: 22px;
      object-fit: contain;
}
    .secrets-header {
      margin-bottom: 32px;
    }

    .secrets-title {
      font-size: 24px;
      font-weight: 600;
      margin: 0 0 12px 0;
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--text-primary, #fff);
    }

    .icon {
      font-size: 28px;
    }

    .secrets-description {
      margin: 0;
      color: var(--text-secondary, #999);
      font-size: 14px;
      line-height: 1.5;
    }

    .secrets-groups {
      display: grid;
      gap: 16px;
      margin-bottom: 32px;
    }

    .secret-group {
      border: 1px solid var(--border-color, #333);
      border-radius: 8px;
      overflow: hidden;
      background: var(--bg-base, #0d0d0d);
    }

    .group-header {
      width: 100%;
      padding: 16px;
      background: var(--bg-elevated, #1e1e1e);
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 16px;
      font-weight: 500;
      color: var(--text-primary, #fff);
      transition: background-color 200ms ease;
    }

    .group-header:hover {
      background: var(--bg-hover, #2a2a2a);
    }

    .group-header.expanded {
      background: var(--accent-bg, #2a5f7f);
    }

    .group-icon {
      font-size: 20px;
      width: 24px;
      text-align: center;
    }

    .group-label {
      flex: 1;
      text-align: left;
    }

    .group-toggle {
      font-size: 12px;
      color: var(--text-secondary, #999);
    }

    .group-fields {
      padding: 16px;
      background: var(--bg-base, #0d0d0d);
      display: grid;
      gap: 12px;
    }

    .field-wrapper {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .field-label {
      font-size: 13px;
      font-weight: 500;
      color: var(--text-primary, #fff);
    }

    .field-input {
      padding: 10px 12px;
      background: var(--input-bg, #1a1a1a);
      border: 1px solid var(--border-color, #333);
      border-radius: 6px;
      color: var(--text-primary, #fff);
      font-size: 14px;
      font-family: monospace;
    }

    .field-input:focus {
      outline: none;
      border-color: var(--accent-color, #0d8cff);
      background: var(--input-bg-focus, #252525);
    }

    .field-input::placeholder {
      color: var(--text-tertiary, #666);
    }

    .field-description {
      font-size: 12px;
      color: var(--text-secondary, #999);
      margin: 0;
      font-style: italic;
    }

    .custom-secret-section {
      padding: 16px;
      background: var(--bg-elevated, #1e1e1e);
      border: 1px dashed var(--border-color, #333);
      border-radius: 8px;
      margin-bottom: 24px;
    }

    .custom-title {
      margin: 0 0 12px 0;
      font-size: 16px;
      font-weight: 500;
      color: var(--text-primary, #fff);
    }

    .custom-fields {
      display: grid;
      grid-template-columns: 1fr 2fr auto;
      gap: 12px;
      align-items: flex-end;
    }

    .btn-add-custom {
      padding: 10px 16px;
      background: var(--accent-color, #0d8cff);
      border: none;
      border-radius: 6px;
      color: white;
      font-weight: 500;
      cursor: pointer;
      transition: background-color 200ms ease;
    }

    .btn-add-custom:hover:not(:disabled) {
      background: var(--accent-hover, #0a6fa8);
    }

    .btn-add-custom:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .secrets-summary {
      padding: 16px;
      background: var(--bg-elevated, #1e1e1e);
      border-radius: 8px;
      margin-bottom: 16px;
    }

    .summary-title {
      margin: 0 0 12px 0;
      font-size: 14px;
      font-weight: 600;
      color: var(--text-primary, #fff);
    }

    .secrets-list {
      display: grid;
      gap: 8px;
    }

    .secret-item {
      display: grid;
      grid-template-columns: 150px 1fr auto;
      gap: 12px;
      align-items: center;
      padding: 8px 12px;
      background: var(--bg-base, #0d0d0d);
      border: 1px solid var(--border-color, #333);
      border-radius: 6px;
      font-size: 13px;
    }

    .secret-key {
      font-weight: 600;
      color: var(--accent-color, #0d8cff);
      font-family: monospace;
    }

    .secret-value-masked {
      color: var(--text-secondary, #999);
      font-family: monospace;
    }

    .btn-remove {
      padding: 4px 8px;
      background: var(--danger-color, #ff4444);
      border: none;
      border-radius: 4px;
      color: white;
      cursor: pointer;
      font-size: 12px;
      transition: background-color 200ms ease;
    }

    .btn-remove:hover {
      background: var(--danger-hover, #cc0000);
    }

    .summary-empty {
      color: var(--text-secondary, #999);
      font-size: 14px;
      padding: 12px;
      text-align: center;
    }

    .security-notice {
      padding: 12px 16px;
      background: var(--info-bg, #1a3a4a);
      border-left: 4px solid var(--accent-color, #0d8cff);
      border-radius: 6px;
      color: var(--text-secondary, #999);
      font-size: 13px;
    }

    .security-notice p {
      margin: 0;
    }

    @media (max-width: 768px) {
      .secrets-container {
        padding: 16px;
      }

      .custom-fields {
        grid-template-columns: 1fr;
      }

      .btn-add-custom {
        grid-column: 1 / -1;
      }

      .secret-item {
        grid-template-columns: 1fr;
        gap: 8px;
      }

      .btn-remove {
        justify-self: flex-start;
      }

    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SecretsFormComponent implements OnInit {
  @Output() secretsChanged = new EventEmitter<Record<string, string>>();

  readonly addedSecrets$ = new BehaviorSubject<Record<string, string>>({});
  readonly activeSecrets$ = new BehaviorSubject<Record<string, string>>({});

  customSecretKey = '';
  customSecretValue = '';

  secretGroups: SecretGroup[] = [
    {
      type: 'docker',
      icon: 'assets/docker.png',
      label: 'Docker Registry',
      expanded: false,
      fields: [
        {
          key: 'DOCKER_USERNAME',
          label: 'Docker Hub Username',
          type: 'text',
          placeholder: 'your-username',
          description: 'Your Docker Hub or private registry username',
        },
        {
          key: 'DOCKER_PASSWORD',
          label: 'Docker Hub Password or Token',
          type: 'password',
          placeholder: 'your-password-or-token',
          description: 'Use a personal access token for better security',
        },
        {
          key: 'REGISTRY_URL',
          label: 'Registry URL (Optional)',
          type: 'text',
          placeholder: 'docker.io or registry.example.com',
          description: 'Custom registry URL if not using Docker Hub',
        },
      ],
    },
    {
      type: 'github',
      icon: 'assets/github.png',
      label: 'GitHub',
      expanded: false,
      fields: [
        {
          key: 'GITHUB_TOKEN',
          label: 'GitHub Personal Access Token',
          type: 'password',
          placeholder: 'ghp_...',
          description: 'Token with repo and workflow permissions',
        },
        {
          key: 'GITHUB_USERNAME',
          label: 'GitHub Username (Optional)',
          type: 'text',
          placeholder: 'your-github-username',
        },
      ],
    },
    {
      type: 'aws',
      icon: 'assets/aws.png',
      label: 'AWS',
      expanded: false,
      fields: [
        {
          key: 'AWS_ACCESS_KEY_ID',
          label: 'AWS Access Key ID',
          type: 'text',
          placeholder: 'AKIA...',
        },
        {
          key: 'AWS_SECRET_ACCESS_KEY',
          label: 'AWS Secret Access Key',
          type: 'password',
          placeholder: 'Your secret access key',
        },
        {
          key: 'AWS_REGION',
          label: 'AWS Region',
          type: 'text',
          placeholder: 'us-east-1',
          description: 'e.g., us-east-1, eu-west-1',
        },
      ],
    },
    {
      type: 'kubernetes',
      icon: 'assets/kubernetes.png',
      label: 'Kubernetes',
      expanded: false,
      fields: [
        {
          key: 'KUBECONFIG_BASE64',
          label: 'Kubeconfig (Base64 Encoded)',
          type: 'password',
          placeholder: 'Base64 encoded kubeconfig content',
          description: 'Run: cat ~/.kube/config | base64',
        },
        {
          key: 'K8S_API_URL',
          label: 'Kubernetes API URL (Optional)',
          type: 'text',
          placeholder: 'https://api.example.com',
        },
      ],
    },
    {
      type: 'gitlab',
      icon: 'assets/gitlab.png',
      label: 'GitLab',
      expanded: false,
      fields: [
        {
          key: 'GITLAB_TOKEN',
          label: 'GitLab Personal Access Token',
          type: 'password',
          placeholder: 'glpat-...',
        },
        {
          key: 'GITLAB_URL',
          label: 'GitLab URL (Optional)',
          type: 'text',
          placeholder: 'https://gitlab.com',
        },
      ],
    },
  ];

  form: FormGroup;
  Object = Object;

  constructor(
    private readonly fb: FormBuilder,
    private readonly cdr: ChangeDetectorRef
  ) {
    this.form = this.createForm();
  }

  ngOnInit(): void {
    this.form.valueChanges
      .pipe(debounceTime(200), distinctUntilChanged())
      .subscribe(() => {
        this.emitSecrets();
      });

    this.emitSecrets();
  }

  private createForm(): FormGroup {
    const group: any = {};
    for (const secretGroup of this.secretGroups) {
      for (const field of secretGroup.fields) {
        group[field.key] = [''];
      }
    }
    return this.fb.group(group);
  }

  toggleGroup(type: string): void {
    const group = this.secretGroups.find((g) => g.type === type);
    if (group) {
      group.expanded = !group.expanded;
      this.cdr.markForCheck();
    }
  }

  getFieldControl(key: string): FormControl | null {
    return this.form.get(key) as FormControl | null;
  }

  addCustomSecret(): void {
    if (!this.customSecretKey || !this.customSecretValue) {
      return;
    }

    const currentSecrets = this.addedSecrets$.value;
    currentSecrets[this.customSecretKey] = this.customSecretValue;
    this.addedSecrets$.next({ ...currentSecrets });

    this.customSecretKey = '';
    this.customSecretValue = '';
    this.emitSecrets();
    this.cdr.markForCheck();
  }

  removeSecret(key: string): void {
    const currentSecrets = this.addedSecrets$.value;
    delete currentSecrets[key];
    this.addedSecrets$.next({ ...currentSecrets });

    // Also remove from form if it exists
    const control = this.form.get(key);
    if (control) {
      control.reset();
    }

    this.emitSecrets();
    this.cdr.markForCheck();
  }

  private emitSecrets(): void {
    const secrets = this.getAllSecrets();
    this.activeSecrets$.next(secrets);
    this.secretsChanged.emit(secrets);
  }

  getAllSecrets(): Record<string, string> {
    const secrets: Record<string, string> = {};

    // Get form values
    for (const [key, control] of Object.entries(this.form.controls)) {
      const value = (control as any).value;
      if (value && typeof value === 'string' && value.trim()) {
        secrets[key] = value.trim();
      }
    }

    // Add custom secrets
    const customSecrets = this.addedSecrets$.value;
    for (const [key, value] of Object.entries(customSecrets)) {
      if (value) {
        secrets[key] = value;
      }
    }

    return secrets;
  }

  maskValue(value: string): string {
    if (value.length <= 8) {
      return '*'.repeat(value.length);
    }
    return value.substring(0, 4) + '***' + value.substring(value.length - 4);
  }
}
