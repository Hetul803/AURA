import { useEffect, useMemo, useState } from 'react';
import { healthcheck, panicStop, resumeRun, sendCommand, subscribeRun } from './state/api';
import ActionPanel from './ui/ActionPanel';
import { pushEvent, store } from './state/store';

declare global {
  interface Window { auraDesktop?: { openLogs: () => Promise<string> } }
}

export default function App() {
  const [input, setInput] = useState('');
  const [out, setOut] = useState('');
  const [runId, setRunId] = useState('');
  const [runStatus, setRunStatus] = useState('idle');
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [connection, setConnection] = useState<'Connected' | 'Disconnected'>('Disconnected');
  const [clarifications, setClarifications] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [needsUser, setNeedsUser] = useState('');
  const [logsPath, setLogsPath] = useState('');

  useEffect(() => {
    let alive = true;
    let delay = 400;
    async function tick() {
      const ok = await healthcheck();
      if (!alive) return;
      setConnection(ok ? 'Connected' : 'Disconnected');
      delay = ok ? 1500 : Math.min(delay * 2, 5000);
      setTimeout(tick, delay);
    }
    tick();
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!startedAt) return;
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 200);
    return () => clearInterval(t);
  }, [startedAt]);

  async function run(choices: Record<string, string> = {}, useMacro = false) {
    const res = await sendCommand(input, choices, useMacro);
    setOut(JSON.stringify(res, null, 2));
    setRunStatus(res.status || (res.ok ? 'running' : 'waiting'));
    if (res.run_id) {
      setRunId(res.run_id);
      setStartedAt(Date.now());
      const unsub = subscribeRun(res.run_id, (evt) => {
        pushEvent(evt);
        setEvents([...(store.eventsByRun[res.run_id] || [])]);
        setRunStatus(evt.status || runStatus);
        if (evt.type === 'needs_user') setNeedsUser(evt.message || 'User action required.');
        if (evt.type === 'resumed') setNeedsUser('');
      });
      void unsub;
    }
    setClarifications(res.clarifications || []);
    if (res.status === 'needs_user') setNeedsUser('Please complete required manual action (login/captcha/permission), then Continue.');
  }

  const autoChoices = Object.fromEntries(clarifications.map((c: any) => [c.key, c.options[0]]));
  const finalText = useMemo(() => events.filter((e) => e.status === 'success').map((e) => e.message).filter(Boolean).join('\n') || out, [events, out]);

  return <div style={{ fontFamily: 'Inter, sans-serif', maxWidth: 950, margin: '0 auto', padding: 16 }}>
    <h1>AURA Overlay</h1>
    <p><strong>Backend:</strong> {connection}</p>
    <div style={{ border: '1px solid #ddd', padding: 12, borderRadius: 8, marginBottom: 10 }}>
      <strong>Run:</strong> {runId || '-'} | <strong>Status:</strong> {runStatus} | <strong>Elapsed:</strong> {elapsed}s
    </div>
    {needsUser && <div role='alert' style={{ background: '#fff4db', border: '1px solid #f0c36d', padding: 12, borderRadius: 8, marginBottom: 10 }}>
      <strong>Action needed:</strong> {needsUser}
      <div style={{ marginTop: 8 }}><button onClick={async () => {
        const r = await resumeRun(runId);
        setOut(JSON.stringify(r, null, 2));
      }}>Continue</button></div>
    </div>}

    <button aria-label='mic'>🎤</button>
    <p>Transcription stub active.</p>
    <input value={input} onChange={e => setInput(e.target.value)} placeholder='Type command' style={{ width: '70%', marginRight: 8 }} />
    <button onClick={() => run()}>Run</button>
    <button onClick={() => panicStop(runId)} disabled={!runId} style={{ marginLeft: 8 }}>Panic Stop</button>
    {!!clarifications.length && <button onClick={() => run(autoChoices)} style={{ marginLeft: 8 }}>Answer Clarifications</button>}
    <button style={{ marginLeft: 8 }} onClick={() => navigator.clipboard.writeText(finalText)}>Copy final answer</button>
    <button style={{ marginLeft: 8 }} onClick={async () => {
      if (window.auraDesktop?.openLogs) setLogsPath(await window.auraDesktop.openLogs());
      else setLogsPath('No desktop bridge. Logs: system default location.');
    }}>Open logs folder</button>
    {logsPath && <p>Logs: {logsPath}</p>}

    <ActionPanel events={events} />
    <pre>{out}</pre>
  </div>;
}
