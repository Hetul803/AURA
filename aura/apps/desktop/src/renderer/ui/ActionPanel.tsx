import type { TimelineEvent } from '../state/types';

const icon = (s: string) => ({ planned: '📝', running: '⏳', success: '✅', fail: '❌', clarification: '❓', done: '🏁', cancelled: '🛑' }[s] || '•');

export default function ActionPanel({ events }: { events: TimelineEvent[] }) {
  const latest = events[events.length - 1];
  return <div>
    <h3>Actions</h3>
    <ul>
      {events.map((e, i) => <li key={`${e.run_id}-${e.step_id || 'run'}-${i}`}>{icon(e.status)} {e.name || e.step_id || e.status} <small>{e.status}</small></li>)}
    </ul>
    <div><strong>Details:</strong> {latest?.message || latest?.status || 'none'}</div>
  </div>;
}
