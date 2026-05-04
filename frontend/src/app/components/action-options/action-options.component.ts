import { Component, Input, Output, EventEmitter, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
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

@Component({
  selector: 'app-action-options',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './action-options.component.html',
  styleUrls: ['./action-options.component.scss']
})
export class ActionOptionsComponent implements OnInit {
  @Input() input!: ActionOptionsInput;
  @Output() accepted = new EventEmitter<{ artifacts: EditedArtifacts; applied: boolean }>();
  @Output() rejected = new EventEmitter<void>();

  isLoading = false;
  errorMessage: string | null = null;
  successMessage: string | null = null;

  get hasGithubOnly(): boolean {
    return !this.input.repoPathAvailable && this.input.githubUrl !== undefined;
  }

  get applyButtonDisabled(): boolean {
    return !this.input.repoPathAvailable;
  }

  get applyButtonHelp(): string {
    return this.input.repoPathAvailable
      ? 'Save artifacts to your repository'
      : 'Clone the repository locally first to apply artifacts';
  }

  constructor(private artifactsService: ArtifactsService) {}

  ngOnInit(): void {}

  async onApplyToRepository(): Promise<void> {
    if (!this.input.repoPath) {
      this.errorMessage = '⚠️ No valid repository path available. Please clone the repository locally first.';
      return;
    }

    this.isLoading = true;
    this.errorMessage = null;

    try {
      const result = await this.artifactsService.applyArtifactsToRepository(
        this.input.repoPath,
        this.input.editedArtifacts
      ).toPromise();

      if (result?.success) {
        this.successMessage = `✅ Artifacts Applied Successfully - ${result.artifacts_written?.length || 0} artifact(s) written`;
        this.accepted.emit({ artifacts: this.input.editedArtifacts, applied: true });
      } else {
        this.errorMessage = '❌ Failed to apply artifacts: ' + (result?.error || 'Unknown error');
      }
    } catch (error) {
      this.errorMessage = `❌ Error applying artifacts: ${error instanceof Error ? error.message : 'Unknown error'}`;
    } finally {
      this.isLoading = false;
    }
  }

  async onDownloadOnly(): Promise<void> {
    this.isLoading = true;
    this.errorMessage = null;

    try {
      const result = await this.artifactsService.downloadArtifacts(
        this.input.editedArtifacts
      ).toPromise();

      if (result?.success) {
        this.successMessage = '✅ Artifacts prepared for download';
        this.accepted.emit({ artifacts: this.input.editedArtifacts, applied: false });
        
        // Trigger download
        if (result.download_url) {
          window.open(result.download_url, '_blank');
        }
      } else {
        this.errorMessage = '❌ Failed to prepare download: ' + (result?.error || 'Unknown error');
      }
    } catch (error) {
      this.errorMessage = `❌ Error preparing download: ${error instanceof Error ? error.message : 'Unknown error'}`;
    } finally {
      this.isLoading = false;
    }
  }

  async onReject(): Promise<void> {
    this.isLoading = true;
    this.errorMessage = null;

    try {
      await this.artifactsService.rejectArtifacts(
        this.input.editedArtifacts
      ).toPromise();

      this.successMessage = '❌ Artifacts rejected. PR creation path is skipped.';
      this.rejected.emit();
    } catch (error) {
      this.errorMessage = `❌ Error rejecting artifacts: ${error instanceof Error ? error.message : 'Unknown error'}`;
    } finally {
      this.isLoading = false;
    }
  }
}
