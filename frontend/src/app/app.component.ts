import { ChangeDetectionStrategy, Component, OnInit } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { HeaderComponent } from './components/header/header.component';
import { ThemeService } from './services/theme.service';
import { ExamplesService } from './services/examples.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, HeaderComponent],
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
  constructor(
    private readonly themeService: ThemeService,
    private readonly examplesService: ExamplesService
  ) {}

  ngOnInit(): void {
    this.themeService.initTheme();
  }

  onExampleSelected(example: string): void {
    this.examplesService.selectExample(example);
  }
}
