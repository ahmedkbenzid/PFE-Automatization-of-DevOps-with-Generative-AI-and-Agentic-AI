import { Component, ChangeDetectionStrategy, Output, EventEmitter } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { ThemeToggleComponent } from '../theme-toggle/theme-toggle.component';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [RouterLink, ThemeToggleComponent, CommonModule],
  template: `
    <header class="app-header">
      <div class="header-container">
        <div class="header-brand">
          <a class="brand-title" [routerLink]="['/']">
  <div class="brand-icon">
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M10.5 2L4 10h5.5L7.5 16l7-8H9L10.5 2z"
            fill="white" stroke="white" stroke-width="0.5" stroke-linejoin="round"/>
    </svg>
  </div>
  <span class="brand-text">Dev<span class="accent">Flow</span> AI</span>
</a>
          <p class="brand-tagline">Multi-Agent DevOps Orchestrator</p>
        </div>
        <div class="header-controls">
          <div class="examples-dropdown">
            <button class="examples-button" (click)="toggleExamplesMenu()">
              <span>💡 Examples</span>
              <span class="dropdown-icon" [class.open]="showExamplesMenu">▼</span>
            </button>
            <div class="examples-menu" *ngIf="showExamplesMenu">
              <div class="menu-section">
                <div class="section-label">CI/CD</div>
                <button type="button" class="menu-item" (click)="selectExample('Create a CI/CD pipeline for my Python project')">
                  🐍 Python CI/CD
                </button>
                <button type="button" class="menu-item" (click)="selectExample('Generate a GitHub Actions workflow for Java/Spring Boot with Maven and SonarQube')">
                  ☕ Java/Spring Boot
                </button>
                <button type="button" class="menu-item" (click)="selectExample('Set up a Node.js test and build pipeline')">
                  📦 Node.js Pipeline
                </button>
              </div>
              
              <div class="menu-section">
                <div class="section-label">Docker</div>
                <button type="button" class="menu-item" (click)="selectExample('Create a Dockerfile for my Python Flask application')">
                  🐍 Python Flask Docker
                </button>
                <button type="button" class="menu-item" (click)="selectExample('Generate a Docker configuration for Java Spring Boot')">
                  ☕ Java Spring Boot Docker
                </button>
                <button type="button" class="menu-item" (click)="selectExample('Build a multi-stage Dockerfile for Go application')">
                  🔵 Go Multi-stage Docker
                </button>
              </div>

              <div class="menu-section">
                <div class="section-label">Kubernetes</div>
                <button type="button" class="menu-item" (click)="selectExample('Generate Kubernetes manifests for my FastAPI app with ConfigMap, Secret, Ingress, and HPA')">
                  ⚡ FastAPI Complete K8s
                </button>
                <button type="button" class="menu-item" (click)="selectExample('Create k8s deployment + service with service type NodePort and Traefik ingress')">
                  🚀 K8s with NodePort & Traefik
                </button>
                <button type="button" class="menu-item" (click)="selectExample('Create manifests for namespace, deployment, service, ingress, and autoscaling for my Java API')">
                  ☕ Java API with Autoscaling
                </button>
                <button type="button" class="menu-item" (click)="selectExample('Generate secure k8s manifests with envFrom, valueFrom, and imagePullSecrets')">
                  🔒 Secure K8s with Secrets
                </button>
              </div>

              <div class="menu-section">
                <div class="section-label">Infrastructure</div>
                <button type="button" class="menu-item" (click)="selectExample('Create Terraform configuration for AWS EC2 deployment')">
                  ☁️ AWS EC2 Terraform
                </button>
                <button type="button" class="menu-item" (click)="selectExample('Set up cloud infrastructure on Azure')">
                  🌩️ Azure Infrastructure
                </button>
              </div>

              <div class="menu-section">
                <div class="section-label">Combined</div>
                <button type="button" class="menu-item" (click)="selectExample('Generate everything I need to deploy my Python project')">
                  🐍 Complete DevOps Setup
                </button>
                <button type="button" class="menu-item" (click)="selectExample('Create complete DevOps setup for my microservice')">
                  🏗️ Microservice DevOps
                </button>
                <button type="button" class="menu-item" (click)="selectExample('Create Dockerfile, CI/CD workflow, and Kubernetes manifests for my Node.js API')">
                  🔗 Full Stack: Docker + CI/CD + K8s
                </button>
              </div>
            </div>
          </div>
          <app-theme-toggle></app-theme-toggle>
        </div>
      </div>
    </header>
  `,
  styles: [`
    .brand-title { 
      display: inline-flex; 
      align-items: center; 
      gap: 10px; 
      text-decoration: none; 
      cursor: pointer; }
    .brand-icon  { 
      width: 36px; 
      height: 36px; 
      border-radius: 8px; 
      background: linear-gradient(135deg, #4f8ef7, #7c3aed); 
      display: flex; 
      align-items: center; 
      justify-content: center; 
      transition: transform 0.18s ease; }
    .brand-title:hover .brand-icon { transform: scale(1.08); }
    .brand-text  { font-family: 'Syne', sans-serif; font-weight: 800; font-size: 22px; letter-spacing: -0.5px; color: #111; }
    .brand-text .accent { 
      color: #4f8ef7; 
    }
    .app-header {
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-default);
      padding: 16px 0;
      position: sticky;
      top: 0;
      z-index: 100;
      transition: all 200ms ease;
    }

    .header-container {
      max-width: 1344px;
      margin: 0 auto;
      padding: 0 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .header-brand {
      flex: 1;
    }

    .brand-title {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-size: 20px;
      font-weight: 700;
      color: var(--text-primary);
      letter-spacing: -0.5px;
    }

    .brand-logo {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      background: linear-gradient(135deg, var(--accent) 0%, #60a5fa 100%);
      border-radius: 6px;
      font-size: 18px;
    }

    .brand-tagline {
      margin: 4px 0 0 40px;
      font-size: 12px;
      color: var(--text-secondary);
      font-weight: 500;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }

    .header-controls {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .examples-dropdown {
      position: relative;
    }

    .examples-button {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 8px 12px;
      background: var(--bg-overlay);
      border: 1px solid var(--border-default);
      border-radius: 6px;
      color: var(--text-secondary);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 150ms ease;

      &:hover {
        background: var(--bg-elevated);
        border-color: var(--accent);
        color: var(--accent);
      }
    }

    .dropdown-icon {
      font-size: 10px;
      transition: transform 200ms ease;

      &.open {
        transform: rotate(180deg);
      }
    }

    .examples-menu {
      position: absolute;
      top: 100%;
      right: 0;
      margin-top: 8px;
      background: var(--bg-surface);
      border: 1px solid var(--border-default);
      border-radius: 8px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
      min-width: 280px;
      max-height: 500px;
      overflow-y: auto;
      z-index: 1000;
      animation: slide-down 200ms ease-out;
    }

    .menu-section {
      padding: 8px 0;
      border-bottom: 1px solid var(--border-subtle);

      &:last-child {
        border-bottom: none;
      }
    }

    .section-label {
      padding: 8px 16px;
      font-size: 11px;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .menu-item {
      display: block;
      width: 100%;
      padding: 10px 16px;
      background: transparent;
      border: none;
      color: var(--text-secondary);
      font-size: 13px;
      text-align: left;
      cursor: pointer;
      transition: all 100ms ease;

      &:hover {
        background: var(--bg-overlay);
        color: var(--accent);
      }

      &:active {
        background: var(--bg-elevated);
      }
    }

    @keyframes slide-down {
      from {
        opacity: 0;
        transform: translateY(-8px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HeaderComponent {
  showExamplesMenu = false;

  @Output() exampleSelected = new EventEmitter<string>();

  toggleExamplesMenu(): void {
    this.showExamplesMenu = !this.showExamplesMenu;
  }

  selectExample(example: string): void {
    this.exampleSelected.emit(example);
    this.showExamplesMenu = false;
  }
}
