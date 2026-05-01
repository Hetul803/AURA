import { useEffect, useMemo, useState } from 'react';
import { approveRun, captureAssistContext, getCurrentContext, getRunState, healthcheck, panicStop, rejectRun, resumeRun, retryRun, sendCommand, subscribeRun } from './state/api';
import ActionPanel from './ui/ActionPanel';
import { pushEvent, store } from './state/store';
import { BACKEND_URL } from '../shared/constants';

declare global {
  interface Window { auraDesktop?: { openLogs: () => Promise<string> } }
}

const QUICK_ACTIONS = [
  'Summarize this',
  'Explain this',
  'Draft a reply to this',
  'Rewrite this better',
  'Research this and answer',
];

export default function App() {
  const [input, setInput] = useState('Summarize this');
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
  const [previewContext, setPreviewContext] = useState<any>(null);
  const [runState, setRunState] = useState<any>(null);
  const [draftText, setDraftText] = useState('');
  const [feedback, setFeedback] = useState('');

  const [prefs, setPrefs] = useState<any[]>([]);
  const [memories, setMemories] = useState<any[]>([]);
  const [sessions, setSessions] = useState<any[]>([]);
  const [storage, setStorage] = useState<any>({});
  const [safety, setSafety] = useState<any[]>([]);

  async function refreshKnowledge() {
    const [p, m, ss, st, se] = await Promise.all([
      fetch(`${BACKEND_URL}/preferences`).then(r => r.json()),
      fetch(`${BACKEND_URL}/memories`).then(r => r.json()),
      fetch(`${BACKEND_URL}/browser/sessions`).then(r => r.json()),
      fetch(`${BACKEND_URL}/storage/stats`).then(r => r.json()),
      fetch(`${BACKEND_URL}/safety/events`).then(r => r.json()),
    ]);
    setPrefs(p); setMemories(m); setSessions(ss); setStorage(st); setSafety(se);
  }

  async function refreshRunState(targetRunId = runId) {
    if (!targetRunId) return;
    const state = await getRunState(targetRunId);
    setRunState(state);
    setDraftText(state?.approval_state?.edited_text || state?.approval_state?.draft_text || state?.draft_state?.draft_text || '');
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
    getCurrentContext().then(setPreviewContext).catch(() => captureAssistContext().then(setPreviewContext).catch(() => undefined));
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
      await refreshRunState(res.run_id);
      subscribeRun(res.run_id, async (evt) => {
        pushEvent(evt);
        setEvents([...(store.eventsByRun[res.run_id] || [])]);
        setRunStatus(evt.status || runStatus);
        if (evt.url) setCurrentUrl(evt.url);
        if (evt.session) setSessionState(evt.session);
        if (evt.type === 'needs_user') setNeedsUser(evt.message || 'User action required.');
        if (evt.type === 'approval_required') setNeedsUser('Draft ready for approval.');
        if (evt.type === 'resumed') setNeedsUser('');
        await refreshRunState(res.run_id);
      });
    }
    setClarifications(res.clarifications || []);
    if (res.status === 'needs_user') setNeedsUser('Please complete the required manual action, then continue.');
    if (res.status === 'awaiting_approval') setNeedsUser('Draft ready for approval.');
    refreshKnowledge();
  }

  const autoChoices = Object.fromEntries(clarifications.map((c: any) => [c.key, c.options[0]]));
  const finalText = useMemo(() => runState?.approval_state?.final_text || draftText || events.filter((e) => e.status === 'success').map((e) => e.message).filter(Boolean).join('\n') || out, [events, out, runState, draftText]);
  const approvalState = runState?.approval_state || {};
  const capturedContext = runState?.captured_context || runState?.planning_context || previewContext;
  const pendingApproval = approvalState.status === 'pending' || runStatus === 'awaiting_approval';
  const toolApproval = approvalState.kind === 'tool_confirmation';
  const generation = runState?.assist?.generation || {};
  const captureMethod = capturedContext?.capture_method || {};
  const pasteState = runState?.pasteback_state || {};

  return <div style={{ fontFamily: 'Inter, sans-serif', maxWidth: 980, margin: '0 auto', padding: 16 }}>
    <h1>AURA Overlay</h1>
    <p><strong>Backend:</strong> {connection}</p>
    <div style={{ border: '1px solid #ddd', padding: 12, borderRadius: 8, marginBottom: 10 }}>
      <strong>Run:</strong> {runId || '-'} | <strong>Status:</strong> {runStatus} | <strong>Elapsed:</strong> {elapsed}s<br/>
      <strong>Current URL:</strong> {currentUrl || capturedContext?.browser_url || '-'} | <strong>Session:</strong> {sessionState}
    </div>

    {needsUser && <div role='alert' style={{ background: '#fff4db', border: '1px solid #f0c36d', padding: 12, borderRadius: 8, marginBottom: 10 }}>
      <strong>{pendingApproval ? 'Approval needed:' : 'Action needed:'}</strong> {needsUser}
      {!pendingApproval && <div style={{ marginTop: 8 }}><button onClick={async () => {
        const r = await resumeRun(runId);
        setOut(JSON.stringify(r, null, 2));
        await refreshRunState(runId);
      }}>Continue</button></div>}
    </div>}

    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
      {QUICK_ACTIONS.map(action => <button key={action} onClick={() => setInput(action)}>{action}</button>)}
      <button onClick={async () => setPreviewContext(await getCurrentContext())}>Refresh context</button>
    </div>

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

    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12, marginBottom: 12 }}>
      <section style={{ border: '1px solid #ddd', borderRadius: 8, padding: 12 }}>
        <h3>Captured Context</h3>
        <div><strong>App:</strong> {capturedContext?.active_app || '-'}</div>
        <div><strong>Window:</strong> {capturedContext?.window_title || '-'}</div>
        <div><strong>Capture Path:</strong> {capturedContext?.capture_path_used || capturedContext?.input_source || '-'}</div>
        <div><strong>Workspace:</strong> {capturedContext?.workspace_hint || capturedContext?.project?.current_folder || '-'}</div>
        <div><strong>Refs:</strong> {(capturedContext?.context_refs || []).map((r: any) => r.repo_full_name || r.type).join(', ') || '-'}</div>
        <div><strong>Clipboard preserved:</strong> {captureMethod.clipboard_preserved === undefined ? '-' : String(captureMethod.clipboard_preserved)}</div>
        <div><strong>Clipboard restored:</strong> {captureMethod.clipboard_restored_after_capture === undefined ? '-' : String(captureMethod.clipboard_restored_after_capture)}</div>
        <div><strong>Browser URL:</strong> {capturedContext?.browser_url || '-'}</div>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{capturedContext?.input_text || 'Select or copy text in another app, then run an assist command.'}</pre>
      </section>

      <section style={{ border: '1px solid #ddd', borderRadius: 8, padding: 12 }}>
        <h3>Draft Review</h3>
        <div><strong>Approval:</strong> {approvalState.status || 'not requested'}</div>
        {toolApproval && <div><strong>Action:</strong> {approvalState.action_type || '-'} / {approvalState.step_name || '-'}</div>}
        {toolApproval && <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(approvalState.requested_args || {}, null, 2)}</pre>}
        <div><strong>Generation:</strong> {generation.provider ? `${generation.provider}${generation.model ? ` / ${generation.model}` : ''}` : '-'}</div>
        <div><strong>Confidence:</strong> {generation.confidence ?? '-'}</div>
        <div><strong>Revalidation:</strong> {pasteState.target_validation_result || pasteState.target_validation || '-'}</div>
        <div><strong>Paste issue:</strong> {pasteState.paste_blocked_reason || pasteState.context_drift_reason || pasteState.clipboard_restore_error_after_paste || '-'}</div>
        {!toolApproval && <textarea aria-label='draft editor' value={draftText} onChange={e => setDraftText(e.target.value)} rows={10} style={{ width: '100%' }} placeholder='Generated draft will appear here.' />}
        <input aria-label='retry feedback' value={feedback} onChange={e => setFeedback(e.target.value)} placeholder='Optional retry feedback (e.g. make it more direct)' style={{ width: '100%', marginTop: 8 }} />
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button disabled={!runId || !pendingApproval} onClick={async () => {
            const r = await approveRun(runId, draftText);
            setOut(JSON.stringify(r, null, 2));
            await refreshRunState(runId);
          }}>{toolApproval ? 'Approve Action' : 'Approve & Paste'}</button>
          {!toolApproval && <button disabled={!runId || !pendingApproval} onClick={async () => {
            const r = await retryRun(runId, feedback);
            setOut(JSON.stringify(r, null, 2));
            await refreshRunState(runId);
          }}>Retry</button>}
          <button disabled={!runId || !pendingApproval} onClick={async () => {
            const r = await rejectRun(runId, feedback);
            setOut(JSON.stringify(r, null, 2));
            await refreshRunState(runId);
          }}>Reject</button>
        </div>
      </section>
    </div>

    <ActionPanel events={events} />

    <h3>Safety Cockpit</h3>
    <ul>{safety.slice(-10).map((s, i) => <li key={i}>{s.kind} / {s.action || s.step_id} / {s.ok === false ? 'fail' : 'ok'}</li>)}</ul>

    <h3>What AURA Knows</h3>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
      <div><h4>Preferences</h4><ul>{prefs.map((p: any) => <li key={p.decision_key}>{p.decision_key}: {p.value} ({Math.round((p.confidence||0)*100)}%)</li>)}</ul></div>
      <div><h4>Memories</h4><ul>{memories.slice(0,20).map((m: any) => <li key={m.id}>{m.key}: {m.value}</li>)}</ul></div>
      <div><h4>Sessions</h4><ul>{sessions.map((s: any) => <li key={s.domain}>{s.domain}</li>)}</ul></div>
      <div><h4>Storage Stats</h4><pre>{JSON.stringify(storage, null, 2)}</pre></div>
    </div>

    <pre>{out}</pre>
  </div>;
}
