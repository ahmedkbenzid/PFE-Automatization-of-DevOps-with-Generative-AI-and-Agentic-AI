import { ChangeDetectionStrategy, Component, OnInit, ViewChild } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { HeaderComponent } from './components/header/header.component';
import { ThemeService } from './services/theme.service';
import { RunFormComponent } from './components/run-form/run-form.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, HeaderComponent, RunFormComponent],
  template: `
    <app-header (exampleSelected)="onExampleSelected($event)"></app-header>
    <router-outlet></router-outlet>
  `,
  styles: [`
    :host {
      display: block;
      min-height: 100vh;
      background: var(--bg-base);
      color: var(--text-primary);
      transition: background-color 200ms ease, color 200ms ease;
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppComponent implements OnInit {
  @ViewChild(RunFormComponent) runFormComponent?: RunFormComponent;

  constructor(private readonly themeService: ThemeService) {}

  ngOnInit(): void {
    this.themeService.initTheme();
  }

  onExampleSelected(example: string): void {
    if (this.runFormComponent) {
      this.runFormComponent.loadExample(example);
    }
  }
}
