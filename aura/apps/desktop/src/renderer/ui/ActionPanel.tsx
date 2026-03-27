import type { TimelineEvent } from '../state/types';

const icon = (s: string) => ({ planned: '📝', running: '⏳', success: '✅', fail: '❌', clarification: '❓', done: '🏁', cancelled: '🛑', needs_user: '🧩', disconnected: '📡' }[s] || '•');

export default function ActionPanel({ events }: { events: TimelineEvent[] }) {
  const latest = events[events.length - 1];
  return <section className='aura-card aura-card-light aura-section' style={{ marginTop: 14 }}>
    <div className='aura-section-title'>
      <div>
        <h3 className='aura-title aura-light-text'>Action timeline</h3>
        <div className='aura-subtitle aura-light-text'>A cleaner run history with status and timing.</div>
      </div>
      <span className='aura-badge aura-badge-accent'>{events.length} events</span>
    </div>
    <ul className='aura-scroll-list'>
      {events.map((e, i) => <li key={`${e.run_id}-${e.step_id || 'run'}-${i}`} className='aura-note'>
        <div className='aura-section-title' style={{ marginBottom: 6 }}>
          <span className='aura-badge aura-badge-accent'>{icon(e.status)} {e.status}</span>
          <span className='aura-meta'>{e.timestamp ? new Date(e.timestamp * 1000).toLocaleTimeString() : 'live'}</span>
        </div>
        <div style={{ fontWeight: 600 }}>{e.name || e.step_id || e.type || e.status}</div>
        {(e.message || e.url || e.session) && <div className='aura-meta' style={{ marginTop: 6 }}>
          {e.message || 'No detail'} {e.url ? `• ${e.url}` : ''} {e.session ? `• ${e.session}` : ''}
        </div>}
      </li>)}
    </ul>
    <div className='aura-note' style={{ marginTop: 12 }}>
      <strong>Latest:</strong> {latest?.message || latest?.status || 'none'}
    </div>
  </section>;
}
