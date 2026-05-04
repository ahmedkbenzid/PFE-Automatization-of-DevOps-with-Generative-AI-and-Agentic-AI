import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { CicdBuilderComponent } from '../cicd-builder/cicd-builder.component';

@Component({
  selector: 'app-cicd-run-page',
  standalone: true,
  imports: [CommonModule, RouterLink, CicdBuilderComponent],
  template: `
    <div class="cicd-run-page">
      <div class="page-header">
        <p class="eyebrow">Docker CI/CD Sandbox</p>
        <h1>Execution {{ executionId }}</h1>
        <a routerLink="/" class="back-link">← Start another run</a>
      </div>

      <app-cicd-builder *ngIf="executionId" [executionId]="executionId"></app-cicd-builder>
    </div>
  `,
  styles: [`
    .cicd-run-page {
      padding: 24px;
    }

    .page-header {
      display: grid;
      gap: 8px;
      margin-bottom: 24px;
    }

    .eyebrow {
      margin: 0;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #7aa2ff;
      font-size: 12px;
      font-weight: 700;
    }

    h1 {
      margin: 0;
      color: #fff;
      font-size: 28px;
    }

    .back-link {
      width: fit-content;
      color: #8ab4ff;
      text-decoration: none;
    }

    .back-link:hover {
      text-decoration: underline;
    }
  `],
})
export class CicdRunPageComponent implements OnInit {
  executionId: string | null = null;

  constructor(private readonly route: ActivatedRoute) {}

  ngOnInit(): void {
    this.executionId = this.route.snapshot.paramMap.get('id');
  }
}