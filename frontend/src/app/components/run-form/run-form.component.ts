import { AsyncPipe, CommonModule, NgIf } from '@angular/common';
import { ChangeDetectionStrategy, Component } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { Subject, of } from 'rxjs';
import { catchError, map, startWith, switchMap, tap } from 'rxjs/operators';

import { RunRequest } from '../../models/run.model';
import { ApiService } from '../../services/api.service';

interface SubmitState {
  submitting: boolean;
  error: string | null;
}

@Component({
  selector: 'app-run-form',
  standalone: true,
  imports: [ReactiveFormsModule, NgIf, AsyncPipe, CommonModule],
  templateUrl: './run-form.component.html',
  styleUrl: './run-form.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RunFormComponent {
  readonly form = this.fb.nonNullable.group({
    prompt: ['', [Validators.required, Validators.minLength(5)]],
    repo_path: [''],
    github_url: [''],
    require_plan_approval: [true],
    create_pr: [false],
  });

  private readonly submitTrigger$ = new Subject<RunRequest>();

  readonly submitState$ = this.submitTrigger$.pipe(
    switchMap((request) =>
      this.api.startRun(request).pipe(
        tap((response) => {
          void this.router.navigate(['/runs', response.run_id]);
        }),
        map((): SubmitState => ({ submitting: false, error: null })),
        startWith({ submitting: true, error: null }),
        catchError((error) =>
          of({
            submitting: false,
            error: this.describeError(error),
          }),
        ),
      ),
    ),
    startWith({ submitting: false, error: null }),
  );

  constructor(
    private readonly fb: FormBuilder,
    private readonly api: ApiService,
    private readonly router: Router,
  ) {}

  loadExample(exampleText: string): void {
    this.form.patchValue({ prompt: exampleText });
    // Scroll to the prompt input
    setTimeout(() => {
      const promptInput = document.getElementById('prompt-input');
      if (promptInput) {
        promptInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        promptInput.focus();
      }
    }, 100);
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const value = this.form.getRawValue();
    console.log('[Frontend] DEBUG: Form values:', value);
    console.log('[Frontend] DEBUG: require_plan_approval =', value.require_plan_approval);
    
    const request: RunRequest = {
      prompt: value.prompt.trim(),
      repo_path: value.repo_path.trim() || undefined,
      github_url: value.github_url.trim() || undefined,
      require_plan_approval: value.require_plan_approval,
      create_pr: value.create_pr,
    };
    
    console.log('[Frontend] DEBUG: Sending request with require_plan_approval =', request.require_plan_approval);
    this.submitTrigger$.next(request);
  }

  private describeError(error: unknown): string {
    if (typeof error === 'object' && error && 'message' in error) {
      return String((error as { message: string }).message);
    }
    return 'Unable to start orchestrator run.';
  }
}
