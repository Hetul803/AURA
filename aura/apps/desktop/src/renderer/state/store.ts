import type { TimelineEvent } from './types';

export const store = {
  activeRunId: '',
  eventsByRun: {} as Record<string, TimelineEvent[]>
};

export function pushEvent(evt: TimelineEvent) {
  if (!store.eventsByRun[evt.run_id]) store.eventsByRun[evt.run_id] = [];
  store.eventsByRun[evt.run_id].push(evt);
}
