import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

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

export interface ApplyArtifactsResponse {
  success: boolean;
  artifacts_written?: string[];
  paths?: Record<string, string>;
  error?: string;
  message?: string;
}

export interface DownloadArtifactsResponse {
  success: boolean;
  download_url?: string;
  error?: string;
  message?: string;
}

export interface RejectArtifactsResponse {
  success: boolean;
  message?: string;
  error?: string;
}

@Injectable({
  providedIn: 'root'
})
export class ArtifactsService {
  private apiUrl = '/api';

  constructor(private http: HttpClient) {}

  /**
   * Apply artifacts to a local repository
   */
  applyArtifactsToRepository(
    repoPath: string,
    artifacts: EditedArtifacts
  ): Observable<ApplyArtifactsResponse> {
    return this.http.post<ApplyArtifactsResponse>(
      `${this.apiUrl}/artifacts/apply`,
      {
        repo_path: repoPath,
        artifacts: artifacts
      }
    );
  }

  /**
   * Download artifacts as a compressed file
   */
  downloadArtifacts(
    artifacts: EditedArtifacts
  ): Observable<DownloadArtifactsResponse> {
    return this.http.post<DownloadArtifactsResponse>(
      `${this.apiUrl}/artifacts/download`,
      {
        artifacts: artifacts
      }
    );
  }

  /**
   * Reject the generated artifacts
   */
  rejectArtifacts(
    artifacts: EditedArtifacts
  ): Observable<RejectArtifactsResponse> {
    return this.http.post<RejectArtifactsResponse>(
      `${this.apiUrl}/artifacts/reject`,
      {
        artifacts: artifacts
      }
    );
  }

  /**
   * Get artifact preview (syntax check, validation, etc.)
   */
  validateArtifacts(
    artifacts: EditedArtifacts
  ): Observable<{ valid: boolean; errors?: string[] }> {
    return this.http.post<{ valid: boolean; errors?: string[] }>(
      `${this.apiUrl}/artifacts/validate`,
      {
        artifacts: artifacts
      }
    );
  }
}
