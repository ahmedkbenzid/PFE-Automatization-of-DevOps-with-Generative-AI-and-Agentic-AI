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
    if (/ERROR|error::/i.test(line)) {
      return 'line-error';
    }

    if (/warning|warn/i.test(line)) {
      return 'line-warning';
    }

    if (/success|completed|done|pass/i.test(line)) {
      return 'line-success';
    }

    return 'line-normal';
  }

  trackByIndex(index: number): number {
    return index;
  }
}
