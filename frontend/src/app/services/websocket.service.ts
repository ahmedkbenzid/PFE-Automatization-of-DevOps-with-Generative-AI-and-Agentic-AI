import { Injectable } from '@angular/core';
import { Observable, defer, timer } from 'rxjs';
import { delayWhen, retryWhen, scan, takeWhile } from 'rxjs/operators';
import { webSocket } from 'rxjs/webSocket';

import { environment } from '../../environments/environment';
import { WsEvent } from '../models/run.model';

@Injectable({
  providedIn: 'root',
})
export class WebsocketService {
  connect(runId: string): Observable<WsEvent> {
    const wsBase = environment.wsUrl.replace(/\/$/, '');
    const url = `${wsBase}/ws/runs/${encodeURIComponent(runId)}`;

    return defer(() =>
      webSocket<WsEvent>({
        url,
        deserializer: ({ data }) => {
          if (typeof data === 'string') {
            return JSON.parse(data) as WsEvent;
          }
          return data as WsEvent;
        },
      }),
    ).pipe(
      retryWhen((errors) =>
        errors.pipe(
          scan((delayMs) => Math.min(delayMs * 2, 30000), 500),
          delayWhen((delayMs) => timer(delayMs)),
        ),
      ),
      takeWhile((event) => event.type !== 'complete', true),
    );
  }
}
