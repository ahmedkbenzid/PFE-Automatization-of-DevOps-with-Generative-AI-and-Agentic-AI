import { NgFor, NgIf } from '@angular/common';
import { ChangeDetectionStrategy, Component, Input, OnChanges, SimpleChanges } from '@angular/core';

import { Artifacts, K8sArtifacts, TerraformArtifacts } from '../../models/run.model';

type MainTab = 'yaml' | 'dockerfile' | 'terraform' | 'kubernetes';

@Component({
  selector: 'app-artifact-viewer',
  standalone: true,
  imports: [NgIf, NgFor],
  templateUrl: './artifact-viewer.component.html',
  styleUrl: './artifact-viewer.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ArtifactViewerComponent implements OnChanges {
  @Input() artifacts: Artifacts | null = null;

  mainTab: MainTab = 'yaml';
  terraformTab: keyof TerraformArtifacts = 'main_tf';
  kubernetesTab: keyof K8sArtifacts = 'deployment_yaml';

  readonly mainTabs: Array<{ key: MainTab; label: string }> = [
    { key: 'yaml', label: 'GitHub Actions YAML' },
    { key: 'dockerfile', label: 'Dockerfile' },
    { key: 'terraform', label: 'Terraform' },
    { key: 'kubernetes', label: 'Kubernetes' },
  ];

  readonly terraformTabs: Array<{ key: keyof TerraformArtifacts; label: string; file: string }> = [
    { key: 'main_tf', label: 'main.tf', file: 'main.tf' },
    { key: 'variables_tf', label: 'variables.tf', file: 'variables.tf' },
    { key: 'outputs_tf', label: 'outputs.tf', file: 'outputs.tf' },
    { key: 'providers_tf', label: 'providers.tf', file: 'providers.tf' },
  ];

  readonly kubernetesTabs: Array<{ key: keyof K8sArtifacts; label: string; file: string }> = [
    { key: 'namespace_yaml', label: 'namespace.yaml', file: 'namespace.yaml' },
    { key: 'deployment_yaml', label: 'deployment.yaml', file: 'deployment.yaml' },
    { key: 'service_yaml', label: 'service.yaml', file: 'service.yaml' },
    { key: 'ingress_yaml', label: 'ingress.yaml', file: 'ingress.yaml' },
    { key: 'configmap_yaml', label: 'configmap.yaml', file: 'configmap.yaml' },
    { key: 'secret_yaml', label: 'secret.yaml', file: 'secret.yaml' },
    { key: 'hpa_yaml', label: 'hpa.yaml', file: 'hpa.yaml' },
  ];

  selectMainTab(tab: MainTab): void {
    this.mainTab = tab;
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['artifacts'] && this.artifacts) {
      if (this.artifacts.yaml) {
        this.mainTab = 'yaml';
      } else if (this.artifacts.dockerfile) {
        this.mainTab = 'dockerfile';
      } else if (this.artifacts.terraform) {
        this.mainTab = 'terraform';
      } else if (this.artifacts.kubernetes) {
        this.mainTab = 'kubernetes';
      }
    }
  }

  selectTerraformTab(tab: keyof TerraformArtifacts): void {
    this.terraformTab = tab;
  }

  selectKubernetesTab(tab: keyof K8sArtifacts): void {
    this.kubernetesTab = tab;
  }

  hasTerraformTab(tab: keyof TerraformArtifacts): boolean {
    return Boolean(this.artifacts?.terraform?.[tab]);
  }

  hasKubernetesTab(tab: keyof K8sArtifacts): boolean {
    return Boolean(this.artifacts?.kubernetes?.[tab]);
  }

  download(content: string | undefined, filename: string): void {
    if (!content) {
      return;
    }

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }
}
