import { NgClass, NgFor } from '@angular/common';
import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

import { OrchestratorResult } from '../../models/run.model';

type AgentState = 'success' | 'failed' | 'pending';

interface AgentDef {
  key: string;
  label: string;
}

const AGENTS: AgentDef[] = [
  { key: 'cicd-agent', label: 'cicd-agent' },
  { key: 'docker-agent', label: 'docker-agent' },
  { key: 'k8s-agent', label: 'k8s-agent' },
  { key: 'iac-agent', label: 'iac-agent' },
];

@Component({
  selector: 'app-agent-status',
  standalone: true,
  imports: [NgFor, NgClass],
  templateUrl: './agent-status.component.html',
  styleUrl: './agent-status.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AgentStatusComponent {
  @Input() result: OrchestratorResult | null = null;

  readonly agents = AGENTS;

  getAgentState(agentKey: string): AgentState {
    const status = this.result?.state?.agent_outputs?.[agentKey]?.status;
    if (status === 'success') {
      return 'success';
    }

    if (status && status !== 'pending') {
      return 'failed';
    }

    return 'pending';
  }

  stateLabel(agentKey: string): string {
    const state = this.getAgentState(agentKey);
    if (state === 'success') {
      return 'Success';
    }
    if (state === 'failed') {
      return 'Failed';
    }
    return 'Pending';
  }

  cardClass(agentKey: string): string {
    const state = this.getAgentState(agentKey);
    if (state === 'success') {
      return 'agent-success';
    }
    if (state === 'failed') {
      return 'agent-failed';
    }
    return 'agent-pending';
  }

  trackByAgent(_: number, item: AgentDef): string {
    return item.key;
  }
}
