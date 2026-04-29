import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

export type Theme = 'light' | 'dark';

@Injectable({
  providedIn: 'root',
})
export class ThemeService {
  private readonly THEME_KEY = 'devflow-theme';
  private readonly defaultTheme: Theme = 'dark';
  private readonly themeSubject = new BehaviorSubject<Theme>(this.defaultTheme);

  readonly theme$: Observable<Theme> = this.themeSubject.asObservable();

  constructor() {}

  initTheme(): void {
    const storedTheme = this.getStoredTheme();
    this.themeSubject.next(storedTheme);
    this.applyTheme(storedTheme);
  }

  getCurrentTheme(): Theme {
    return this.themeSubject.value;
  }

  setTheme(theme: Theme): void {
    if (theme !== this.themeSubject.value) {
      this.themeSubject.next(theme);
      localStorage.setItem(this.THEME_KEY, theme);
      this.applyTheme(theme);
    }
  }

  toggleTheme(): void {
    const newTheme: Theme = this.themeSubject.value === 'dark' ? 'light' : 'dark';
    this.setTheme(newTheme);
  }

  private getStoredTheme(): Theme {
    const stored = localStorage.getItem(this.THEME_KEY) as Theme | null;
    if (stored === 'light' || stored === 'dark') {
      return stored;
    }

    // Check system preference
    if (typeof window !== 'undefined' && window.matchMedia) {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      return prefersDark ? 'dark' : 'light';
    }

    return this.defaultTheme;
  }

  private applyTheme(theme: Theme): void {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', theme);
      document.body.classList.remove('theme-light', 'theme-dark');
      document.body.classList.add(`theme-${theme}`);
    }
  }
}
