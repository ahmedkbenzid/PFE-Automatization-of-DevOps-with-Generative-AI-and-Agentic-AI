import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NgFor, NgIf, NgClass } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { EditedArtifacts } from '../action-options/action-options.component';
import { environment } from '../../../environments/environment';

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
        <div class="min-w-0 flex-1">
          <p class="text-sm font-bold text-devflow-text">Artifact Assistant</p>
          <p class="text-xs text-devflow-text-muted">Describe changes in plain language</p>
        </div>
        <button
          type="button"
          (click)="clearChat()"
          [disabled]="loading || messages.length === 0"
          class="rounded-lg border border-devflow-border px-2.5 py-1 text-xs font-semibold text-devflow-text-muted transition-colors hover:border-devflow-accent hover:text-devflow-accent disabled:cursor-not-allowed disabled:opacity-40"
          title="Clear chat history"
        >
          Clear
        </button>
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

  private readonly apiUrl = environment.apiUrl;

  // Local snapshot kept in sync with @Input so we can mutate and emit
  private current: EditedArtifacts | null = null;

  constructor(
    private readonly http: HttpClient,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnChanges(): void {
    // Always keep current in sync with latest artifacts from parent
    if (this.artifacts) {
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
    this.cdr.markForCheck();
    this.scrollToBottom();

    try {
      const reply = await this.callBackend(text);
      loadingMsg.loading = false;
      loadingMsg.content = reply.explanation;

      if (reply.artifacts) {
        // Deep-merge returned artifacts with current to preserve unchanged sub-fields
        this.current = this.mergeArtifacts(this.current, reply.artifacts);
        this.artifactsChanged.emit(structuredClone(this.current));
      }
    } catch (e: any) {
      loadingMsg.loading = false;
      const status = e?.status;
      if (status === 502 || status === 504) {
        loadingMsg.content = 'The AI service is temporarily unavailable. Please try again.';
      } else if (status === 500) {
        loadingMsg.content = 'Server error — check that GROQ_API_KEY is configured.';
      } else {
        loadingMsg.content = 'Something went wrong. Please try again.';
      }
    } finally {
      this.loading = false;
      this.cdr.markForCheck();
      this.scrollToBottom();
    }
  }

  clearChat(): void {
    if (this.loading) return;

    this.messages = [];
    this.userInput = '';
    this.cdr.markForCheck();
  }

  /**
   * Call the backend /api/chat/artifacts endpoint which uses the
   * server-side Groq LLM to understand and apply artifact corrections.
   */
  private callBackend(userMessage: string): Promise<{ explanation: string; artifacts: EditedArtifacts | null }> {
    // Build conversation history for multi-turn context.
    // Exclude the LAST user message (the current one) because the backend
    // re-includes it with artifact context to avoid duplication.
    const allNonLoading = this.messages.filter(m => !m.loading);
    const conversationHistory = allNonLoading
      .slice(0, -1)
      .map(m => ({ role: m.role, content: m.content }));

    const body = {
      message: userMessage,
      artifacts: this.current ?? {},
      conversation_history: conversationHistory,
    };

    return new Promise((resolve, reject) => {
      this.http
        .post<{ explanation: string; artifacts: EditedArtifacts | null }>(
          `${this.apiUrl}/api/chat/artifacts`,
          body,
        )
        .subscribe({
          next: (res) => resolve({
            explanation: res.explanation ?? 'Done.',
            artifacts: res.artifacts ?? null,
          }),
          error: (err) => reject(err),
        });
    });
  }

  /**
   * Deep-merge returned artifacts with the current ones so partial LLM
   * responses don't wipe unchanged nested fields (terraform, kubernetes).
   */
  private mergeArtifacts(
    base: EditedArtifacts | null,
    updates: EditedArtifacts,
  ): EditedArtifacts {
    if (!base) return updates;

    return {
      yaml:       updates.yaml       ?? base.yaml,
      dockerfile: updates.dockerfile ?? base.dockerfile,
      terraform: {
        ...base.terraform,
        ...(updates.terraform ?? {}),
      },
      kubernetes: {
        ...base.kubernetes,
        ...(updates.kubernetes ?? {}),
      },
      metadata: updates.metadata ?? base.metadata,
    };
  }

  private scrollToBottom(): void {
    setTimeout(() => {
      const el = document.getElementById('chat-scroll');
      if (el) el.scrollTop = el.scrollHeight;
    }, 50);
  }
}
