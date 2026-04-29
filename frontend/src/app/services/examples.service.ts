import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

@Injectable({
  providedIn: 'root',
})
export class ExamplesService {
  private readonly exampleSelected$ = new Subject<string>();

  readonly selectedExample$ = this.exampleSelected$.asObservable();

  selectExample(example: string): void {
    this.exampleSelected$.next(example);
  }
}
