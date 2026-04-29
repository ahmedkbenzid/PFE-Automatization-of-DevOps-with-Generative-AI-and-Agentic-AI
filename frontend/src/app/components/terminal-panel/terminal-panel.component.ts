import { NgClass, NgFor } from '@angular/common';
import {
  AfterViewChecked,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  Input,
  OnChanges,
  SimpleChanges,
  ViewChild,
} from '@angular/core';

@Component({
  selector: 'app-terminal-panel',
  standalone: true,
  imports: [NgFor, NgClass],
  templateUrl: './terminal-panel.component.html',
  styleUrl: './terminal-panel.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TerminalPanelComponent implements OnChanges, AfterViewChecked {
  @Input() lines: string[] = [];

  @ViewChild('terminalPane') private terminalPane?: ElementRef<HTMLDivElement>;

  bufferedLines: string[] = [];

  private readonly maxLines = 500;
  private lastRenderedCount = 0;

  ngOnChanges(changes: SimpleChanges): void {
    if (!changes['lines']) {
      return;
    }

    const source = this.lines ?? [];
    this.bufferedLines = source.length > this.maxLines ? source.slice(-this.maxLines) : [...source];
  }

  ngAfterViewChecked(): void {
    if (!this.terminalPane?.nativeElement) {
      return;
    }

    if (this.bufferedLines.length !== this.lastRenderedCount) {
      this.terminalPane.nativeElement.scrollTop = this.terminalPane.nativeElement.scrollHeight;
      this.lastRenderedCount = this.bufferedLines.length;
    }
  }

  lineClass(line: string): string {
    if (/error|fail/i.test(line)) {
      return 'log--error';
    }

    if (/warning|warn/i.test(line)) {
      return 'log--warn';
    }

    if (/success|completed|done|pass/i.test(line)) {
      return 'log--success';
    }
    
    if (/===|---|orchestrator/i.test(line)) {
      return 'log--system';
    }

    return 'log--normal';
  }

  trackByIndex(index: number): number {
    return index;
  }
}
