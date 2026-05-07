import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NgFor, NgIf, NgClass } from '@angular/common';
import { EditedArtifacts } from '../action-options/action-options.component';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  loading?: boolean;
}

@Component({
  selector: 'app-run-chat',
  standalone: true,
  imports: [FormsModule, NgFor, NgIf, NgClass],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!-- Toggle button -->
    <button
      (click)="open = !open"
      class="fixed bottom-6 right-6 z-50 flex h-12 w-12 items-center justify-center rounded-full bg-devflow-accent shadow-lg transition-transform hover:scale-105 active:scale-95"
      title="AI Assistant"
    >
      <svg *ngIf="!open" xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
      <svg *ngIf="open" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    </button>

    <!-- Chat panel -->
    <div
      *ngIf="open"
      class="fixed bottom-24 right-6 z-50 flex h-[520px] w-[380px] flex-col rounded-2xl border border-devflow-border bg-devflow-surface shadow-2xl"
    >
      <!-- Header -->
      <div class="flex items-center gap-3 rounded-t-2xl border-b border-devflow-border bg-devflow-elevated px-4 py-3">
        <div class="flex h-8 w-8 items-center justify-center rounded-full bg-devflow-accent">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>
          </svg>
        </div>
        <div>
          <p class="text-sm font-bold text-devflow-text">Artifact Assistant</p>
          <p class="text-xs text-devflow-text-muted">Describe changes in plain language</p>
        </div>
      </div>

      <!-- Messages -->
      <div #scrollContainer class="flex-1 overflow-y-auto px-4 py-3 space-y-3" id="chat-scroll">
        <div *ngIf="messages.length === 0" class="flex h-full flex-col items-center justify-center gap-2 text-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-10 w-10 text-devflow-text-muted opacity-40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          <p class="text-sm font-medium text-devflow-text-muted">Ask me to modify your artifacts</p>
          <p class="text-xs text-devflow-text-muted opacity-70">e.g. "Add a health check to the Dockerfile" or "Set replicas to 3 in Kubernetes"</p>
        </div>

        <div *ngFor="let msg of messages" class="flex flex-col gap-1" [ngClass]="msg.role === 'user' ? 'items-end' : 'items-start'">
          <div
            class="max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed"
            [ngClass]="{
              'bg-devflow-accent text-white rounded-br-sm': msg.role === 'user',
              'bg-devflow-elevated text-devflow-text rounded-bl-sm': msg.role === 'assistant' && !msg.loading,
              'bg-devflow-elevated text-devflow-text-muted rounded-bl-sm animate-pulse': msg.loading
            }"
          >
            <span *ngIf="!msg.loading">{{ msg.content }}</span>
            <span *ngIf="msg.loading" class="flex items-center gap-1">
              <span class="h-1.5 w-1.5 rounded-full bg-devflow-text-muted animate-bounce [animation-delay:0ms]"></span>
              <span class="h-1.5 w-1.5 rounded-full bg-devflow-text-muted animate-bounce [animation-delay:150ms]"></span>
              <span class="h-1.5 w-1.5 rounded-full bg-devflow-text-muted animate-bounce [animation-delay:300ms]"></span>
            </span>
          </div>
        </div>
      </div>

      <!-- Input -->
      <div class="rounded-b-2xl border-t border-devflow-border bg-devflow-elevated px-3 py-3">
        <div class="flex items-end gap-2">
          <textarea
            [(ngModel)]="userInput"
            (keydown.enter)="onEnter($event)"
            [disabled]="loading"
            rows="1"
            placeholder="e.g. Set memory limit to 512Mi..."
            class="flex-1 resize-none rounded-xl border border-devflow-border bg-devflow-surface px-3 py-2 text-sm text-devflow-text placeholder-devflow-text-muted outline-none focus:border-devflow-accent focus:ring-1 focus:ring-devflow-accent disabled:opacity-50"
          ></textarea>
          <button
            (click)="send()"
            [disabled]="!userInput.trim() || loading"
            class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-devflow-accent text-white shadow transition-all hover:opacity-90 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
        <p class="mt-1.5 text-center text-[10px] text-devflow-text-muted">Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  `,
})
export class RunChatComponent implements OnChanges {
  @Input() artifacts: EditedArtifacts | null = null;
  @Output() artifactsChanged = new EventEmitter<EditedArtifacts>();

  open = false;
  loading = false;
  userInput = '';
  messages: ChatMessage[] = [];

  // Local snapshot kept in sync with @Input so we can mutate and emit
  private current: EditedArtifacts | null = null;

  ngOnChanges(): void {
    // Only sync when user isn't mid-edit (chat hasn't produced a diff yet)
    if (this.artifacts && !this.current) {
      this.current = structuredClone(this.artifacts);
    }
  }

    onEnter(event: Event): void {
    const ke = event as KeyboardEvent;
    if (!ke.shiftKey) {
        event.preventDefault();
        this.send();
    }
    }

  async send(): Promise<void> {
    const text = this.userInput.trim();
    if (!text || this.loading) return;

    this.messages.push({ role: 'user', content: text });
    this.userInput = '';
    this.loading = true;

    const loadingMsg: ChatMessage = { role: 'assistant', content: '', loading: true };
    this.messages.push(loadingMsg);
    this.scrollToBottom();

    try {
      const reply = await this.callClaude(text);
      loadingMsg.loading = false;
      loadingMsg.content = reply.explanation;

      if (reply.artifacts) {
        this.current = reply.artifacts;
        this.artifactsChanged.emit(structuredClone(this.current));
      }
    } catch (e) {
      loadingMsg.loading = false;
      loadingMsg.content = 'Something went wrong. Please try again.';
    } finally {
      this.loading = false;
      this.scrollToBottom();
    }
  }

  private async callClaude(userMessage: string): Promise<{ explanation: string; artifacts: EditedArtifacts | null }> {
    const systemPrompt = `You are a DevOps assistant that modifies CI/CD, Dockerfile, Terraform, and Kubernetes artifacts based on user requests.

You will receive the current artifacts as JSON and a user instruction.
You MUST respond with ONLY a valid JSON object in this exact shape:
{
  "explanation": "brief human-readable summary of what you changed",
  "artifacts": { ...the full updated EditedArtifacts object... }
}

Rules:
- Always return the COMPLETE artifacts object, not just the changed fields.
- If a field is unchanged, keep it exactly as-is.
- If the user's request does not require any artifact change, set "artifacts" to null and explain why.
- Never add markdown fences or any text outside the JSON object.`;

    const userContent = `Current artifacts:
${JSON.stringify(this.current, null, 2)}

User request: ${userMessage}`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 4096,
        system: systemPrompt,
        messages: [{ role: 'user', content: userContent }],
      }),
    });

    if (!response.ok) throw new Error(`API error ${response.status}`);

    const data = await response.json();
    const raw = data.content?.find((b: any) => b.type === 'text')?.text ?? '{}';

    try {
      const parsed = JSON.parse(raw);
      return {
        explanation: parsed.explanation ?? 'Done.',
        artifacts: parsed.artifacts ?? null,
      };
    } catch {
      return { explanation: raw, artifacts: null };
    }
  }

  private scrollToBottom(): void {
    setTimeout(() => {
      const el = document.getElementById('chat-scroll');
      if (el) el.scrollTop = el.scrollHeight;
    }, 50);
  }
}