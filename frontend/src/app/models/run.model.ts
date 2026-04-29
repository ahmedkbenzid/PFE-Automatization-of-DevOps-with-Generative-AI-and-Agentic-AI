export interface RunRequest {
  prompt: string;
  repo_path?: string;
  github_url?: string;
  require_plan_approval?: boolean;
  create_pr?: boolean;
  runtime_secrets?: Record<string, string>;
}

export interface LogEvent {
  type: 'log';
  line: string;
}

export interface CompleteEvent {
  type: 'complete';
  result: OrchestratorResult;
}

export type WsEvent = LogEvent | CompleteEvent;

export interface OrchestratorResult {
  status: string;
  used_planner?: boolean;
  complexity_score?: number;
  execution_plan?: any;
  state?: any;
}

export interface Artifacts {
  yaml?: string;
  dockerfile?: string;
  terraform?: TerraformArtifacts;
  kubernetes?: K8sArtifacts;
  metadata?: any;
}

export interface TerraformArtifacts {
  main_tf?: string;
  variables_tf?: string;
  outputs_tf?: string;
  providers_tf?: string;
}

export interface K8sArtifacts {
  namespace_yaml?: string;
  deployment_yaml?: string;
  service_yaml?: string;
  ingress_yaml?: string;
  configmap_yaml?: string;
  secret_yaml?: string;
  hpa_yaml?: string;
}
