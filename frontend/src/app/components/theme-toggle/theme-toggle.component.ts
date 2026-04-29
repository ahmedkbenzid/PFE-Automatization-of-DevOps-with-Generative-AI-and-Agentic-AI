import { Component, ChangeDetectionStrategy } from '@angular/core';
import { AsyncPipe, NgIf } from '@angular/common';
import { ThemeService, Theme } from '../../services/theme.service';

@Component({
  selector: 'app-theme-toggle',
  standalone: true,
  imports: [AsyncPipe, NgIf],
  template: `
    <button
      class="theme-toggle"
      [attr.aria-label]="(theme$ | async) === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
      (click)="toggleTheme()"
      type="button"
    >
      <svg
        *ngIf="(theme$ | async) === 'dark'"
        class="icon icon-moon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
      </svg>
      <svg
        *ngIf="(theme$ | async) === 'light'"
        class="icon icon-sun"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <circle cx="12" cy="12" r="5"></circle>
        <line x1="12" y1="1" x2="12" y2="3"></line>
        <line x1="12" y1="21" x2="12" y2="23"></line>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
        <line x1="1" y1="12" x2="3" y2="12"></line>
        <line x1="21" y1="12" x2="23" y2="12"></line>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
      </svg>
    </button>
  `,
  styles: [`
    .theme-toggle {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      border-radius: 6px;
      border: 1px solid var(--border-default);
      background: var(--bg-surface);
      color: var(--text-secondary);
      cursor: pointer;
      transition: all 200ms ease;
      padding: 0;

      &:hover {
        background: var(--bg-elevated);
        color: var(--text-primary);
        border-color: var(--border-strong);
      }

      &:active {
        transform: scale(0.95);
      }

      .icon {
        width: 18px;
        height: 18px;
      }
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ThemeToggleComponent {
  readonly theme$ = this.themeService.theme$;

  constructor(private readonly themeService: ThemeService) {}

  toggleTheme(): void {
    this.themeService.toggleTheme();
  }
}
