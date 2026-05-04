import { AsyncPipe, CommonModule, NgIf } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, OnDestroy } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { Subject, of, Subscription, BehaviorSubject } from 'rxjs';
import { catchError, map, startWith, switchMap, tap } from 'rxjs/operators';

import { RunRequest } from '../../models/run.model';
import { ApiService } from '../../services/api.service';
import { ExamplesService } from '../../services/examples.service';
import { SecretsFormComponent } from '../secrets-form/secrets-form.component';

interface SubmitState {
  submitting: boolean;
  error: string | null;
}

@Component({
  selector: 'app-run-form',
  standalone: true,
  imports: [ReactiveFormsModule, NgIf, AsyncPipe, CommonModule, SecretsFormComponent],
  templateUrl: './run-form.component.html',
  styleUrl: './run-form.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RunFormComponent implements OnInit, OnDestroy {
  private examplesSub?: Subscription;
  
  readonly collectedSecrets$ = new BehaviorSubject<Record<string, string>>({});

  readonly form = this.fb.nonNullable.group({
    prompt: ['', [Validators.required, Validators.minLength(5)]],
    repo_path: [''],
    github_url: [''],
    require_plan_approval: [false],
    create_pr: [false],
    build_in_docker: [true],
  });

  private readonly submitTrigger$ = new Subject<RunRequest>();

  readonly submitState$ = this.submitTrigger$.pipe(
    switchMap((request) => {
      return this.api.startRun(request).pipe(
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
      );
    }),
    startWith({ submitting: false, error: null }),
  );

  constructor(
    private readonly fb: FormBuilder,
    private readonly api: ApiService,
    private readonly router: Router,
    private readonly examplesService: ExamplesService,
  ) {}

  ngOnInit(): void {
    this.examplesSub = this.examplesService.selectedExample$.subscribe((example) => {
      this.loadExample(example);
    });
  }

  ngOnDestroy(): void {
    if (this.examplesSub) {
      this.examplesSub.unsubscribe();
    }
  }

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

  onSecretsChanged(secrets: Record<string, string>): void {
    this.collectedSecrets$.next(secrets);
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const value = this.form.getRawValue();
    console.log('[Frontend] DEBUG: Form values:', value);
    console.log('[Frontend] DEBUG: require_plan_approval =', value.require_plan_approval);
    console.log('[Frontend] DEBUG: build_in_docker =', value.build_in_docker);
    
    const request: RunRequest = {
      prompt: value.prompt.trim(),
      repo_path: value.repo_path.trim() || undefined,
      github_url: value.github_url.trim() || undefined,
      require_plan_approval: value.require_plan_approval,
      create_pr: value.create_pr,
      build_in_docker: value.build_in_docker,
      runtime_secrets: this.collectedSecrets$.value,
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
