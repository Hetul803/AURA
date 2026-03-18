import { useEffect, useMemo, useState } from 'react';
import { healthcheck, panicStop, resumeRun, sendCommand, subscribeRun } from './state/api';
import ActionPanel from './ui/ActionPanel';
import { pushEvent, store } from './state/store';
import { BACKEND_URL } from '../shared/constants';

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
  const [currentUrl, setCurrentUrl] = useState('');
  const [sessionState, setSessionState] = useState('unknown');

  const [prefs, setPrefs] = useState<any[]>([]);
  const [memories, setMemories] = useState<any[]>([]);
  const [macros, setMacros] = useState<any[]>([]);
  const [sessions, setSessions] = useState<any[]>([]);
  const [storage, setStorage] = useState<any>({});
  const [safety, setSafety] = useState<any[]>([]);

  async function refreshKnowledge() {
    const [p, m, mc, ss, st, se] = await Promise.all([
      fetch(`${BACKEND_URL}/preferences`).then(r => r.json()),
      fetch(`${BACKEND_URL}/memories`).then(r => r.json()),
      fetch(`${BACKEND_URL}/macros`).then(r => r.json()),
      fetch(`${BACKEND_URL}/browser/sessions`).then(r => r.json()),
      fetch(`${BACKEND_URL}/storage/stats`).then(r => r.json()),
      fetch(`${BACKEND_URL}/safety/events`).then(r => r.json()),
    ]);
    setPrefs(p); setMemories(m); setMacros(mc); setSessions(ss); setStorage(st); setSafety(se);
  }

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
    refreshKnowledge();
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
      subscribeRun(res.run_id, (evt) => {
        pushEvent(evt);
        setEvents([...(store.eventsByRun[res.run_id] || [])]);
        setRunStatus(evt.status || runStatus);
        if (evt.url) setCurrentUrl(evt.url);
        if (evt.session) setSessionState(evt.session);
        if (evt.type === 'needs_user') setNeedsUser(evt.message || 'User action required.');
        if (evt.type === 'resumed') setNeedsUser('');
      });
    }
    setClarifications(res.clarifications || []);
    if (res.status === 'needs_user') setNeedsUser('Please complete required manual action (login/captcha/permission), then Continue.');
    refreshKnowledge();
  }

  const autoChoices = Object.fromEntries(clarifications.map((c: any) => [c.key, c.options[0]]));
  const finalText = useMemo(() => events.filter((e) => e.status === 'success').map((e) => e.message).filter(Boolean).join('\n') || out, [events, out]);

  return <div style={{ fontFamily: 'Inter, sans-serif', maxWidth: 1100, margin: '0 auto', padding: 16 }}>
    <h1>AURA Overlay</h1>
    <p><strong>Backend:</strong> {connection}</p>
    <div style={{ border: '1px solid #ddd', padding: 12, borderRadius: 8, marginBottom: 10 }}>
      <strong>Run:</strong> {runId || '-'} | <strong>Status:</strong> {runStatus} | <strong>Elapsed:</strong> {elapsed}s<br/>
      <strong>Current URL:</strong> {currentUrl || '-'} | <strong>Session:</strong> {sessionState}
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
    <input value={input} onChange={e => setInput(e.target.value)} placeholder='Type command' style={{ width: '65%', marginRight: 8 }} />
    <button onClick={() => run()}>Run</button>
    <button onClick={() => panicStop(runId)} disabled={!runId} style={{ marginLeft: 8 }}>Panic Stop</button>
    {!!clarifications.length && <button onClick={() => run(autoChoices)} style={{ marginLeft: 8 }}>Answer Clarifications</button>}
    <button style={{ marginLeft: 8 }} onClick={() => navigator.clipboard.writeText(finalText)}>Copy final answer</button>
    <button style={{ marginLeft: 8 }} onClick={async () => {
      if (window.auraDesktop?.openLogs) setLogsPath(await window.auraDesktop.openLogs());
      else setLogsPath('No desktop bridge. Logs: system default location.');
    }}>Open logs folder</button>
    <button style={{ marginLeft: 8 }} onClick={refreshKnowledge}>Refresh Panels</button>
    {logsPath && <p>Logs: {logsPath}</p>}

    <ActionPanel events={events} />

    <h3>Safety Cockpit</h3>
    <ul>{safety.slice(-10).map((s, i) => <li key={i}>{s.kind} / {s.action || s.step_id} / {s.ok === false ? 'fail' : 'ok'}</li>)}</ul>

    <h3>What AURA Knows</h3>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
      <div><h4>Preferences</h4><ul>{prefs.map((p: any) => <li key={p.decision_key}>{p.decision_key}: {p.value} ({Math.round((p.confidence||0)*100)}%) <button onClick={async()=>{await fetch(`${BACKEND_URL}/preferences/${p.decision_key}`, {method:'DELETE'}); refreshKnowledge();}}>Delete</button></li>)}</ul></div>
      <div><h4>Memories</h4><ul>{memories.slice(0,20).map((m: any) => <li key={m.id}>{m.key}: {m.value} <button onClick={async()=>{await fetch(`${BACKEND_URL}/memories/${m.id}`, {method:'DELETE'}); refreshKnowledge();}}>Delete</button></li>)}</ul></div>
      <div><h4>Macros</h4><ul>{macros.map((m: any) => <li key={m.id}>{m.name} ({m.trigger_signature})</li>)}</ul></div>
      <div><h4>Sessions</h4><ul>{sessions.map((s: any) => <li key={s.domain}>{s.domain} <button onClick={async()=>{await fetch(`${BACKEND_URL}/browser/session/${s.domain}`, {method:'DELETE'}); refreshKnowledge();}}>Clear</button></li>)}</ul><button onClick={async()=>{await fetch(`${BACKEND_URL}/browser/sessions`, {method:'DELETE'}); refreshKnowledge();}}>Clear all sessions</button></div>
    </div>
    <h4>Storage Stats</h4>
    <pre>{JSON.stringify(storage, null, 2)}</pre>

    <pre>{out}</pre>
  </div>;
}
