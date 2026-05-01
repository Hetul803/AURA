import { useEffect, useMemo, useState } from 'react';
import { approveRun, captureAssistContext, createWorkflow, getCurrentContext, getDevices, getMemoryItems, getRunState, getTools, getWorkflowSuggestions, getWorkflows, healthcheck, panicStop, rejectRun, resumeRun, retryRun, runWorkflow, sendCommand, subscribeRun } from './state/api';
import ActionPanel from './ui/ActionPanel';
import { pushEvent, store } from './state/store';
import { BACKEND_URL } from '../shared/constants';

declare global {
  interface Window { auraDesktop?: { openLogs: () => Promise<string> } }
}

const QUICK_ACTIONS = [
  'Clone this repo locally',
  'Reply to this email',
  'Build me a SaaS landing page for this idea',
  'Use my ChatGPT subscription to write a reply to this email',
  'Create a reusable workflow from this',
];

const PANELS = ['Run', 'Workflows', 'Memory', 'Safety', 'System'];

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
  const [activePanel, setActivePanel] = useState('Run');

  const [prefs, setPrefs] = useState<any[]>([]);
  const [memories, setMemories] = useState<any[]>([]);
  const [sessions, setSessions] = useState<any[]>([]);
  const [storage, setStorage] = useState<any>({});
  const [safety, setSafety] = useState<any[]>([]);
  const [tools, setTools] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [memoryItems, setMemoryItems] = useState<any[]>([]);
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [workflowSuggestions, setWorkflowSuggestions] = useState<any[]>([]);

  async function refreshKnowledge() {
    const [p, m, ss, st, se, ts, ds, mi, wf, ws] = await Promise.all([
      fetch(`${BACKEND_URL}/preferences`).then(r => r.json()),
      fetch(`${BACKEND_URL}/memories`).then(r => r.json()),
      fetch(`${BACKEND_URL}/browser/sessions`).then(r => r.json()),
      fetch(`${BACKEND_URL}/storage/stats`).then(r => r.json()),
      fetch(`${BACKEND_URL}/safety/events`).then(r => r.json()),
      getTools(),
      getDevices(),
      getMemoryItems(),
      getWorkflows(),
      getWorkflowSuggestions(),
    ]);
    setPrefs(p); setMemories(m); setSessions(ss); setStorage(st); setSafety(se);
    setTools(ts); setDevices(ds);
    setMemoryItems(mi);
    setWorkflows(wf);
    setWorkflowSuggestions(ws);
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
    const context = previewContext || await getCurrentContext().catch(() => null);
    if (context) setPreviewContext(context);
    const res = await sendCommand(input, choices, useMacro, context);
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
  const pendingRisk = approvalState.risk_reason || approvalState.action_type || '';
  const approvalMessage = toolApproval
    ? `Approve ${approvalState.step_name || approvalState.action_type || 'this action'}`
    : 'Review the draft, edit if needed, then approve paste-back.';
  const launchFlow = runState?.plan?.signature || (capturedContext?.browser_url?.includes('github.com') ? 'github:clone' : 'desktop');
  const commandPlaceholder = capturedContext?.browser_url?.includes('github.com')
    ? 'Try: Clone this repo locally'
    : 'Tell AURA what to do with the current app, page, file, or selection';
  const chrome = { border: '1px solid #d7dee8', borderRadius: 8, padding: 12, background: '#ffffff' };
  const activeTabStyle = { border: '1px solid #152033', background: '#152033', color: '#fff', borderRadius: 6, padding: '7px 10px' };
  const tabStyle = { border: '1px solid #ccd5e1', background: '#fff', color: '#152033', borderRadius: 6, padding: '7px 10px' };

  return <div style={{ fontFamily: 'Inter, system-ui, sans-serif', maxWidth: 1120, margin: '0 auto', padding: 16, color: '#172033', background: '#f6f8fb', minHeight: '100vh' }}>
    <header style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', marginBottom: 12 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: 28 }}>AURA</h1>
        <div style={{ color: '#526173', marginTop: 4 }}>Personal AI operating layer for this desktop</div>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        <span style={{ padding: '6px 10px', borderRadius: 999, border: '1px solid #ccd5e1', background: connection === 'Connected' ? '#e8f6ef' : '#fff0f0' }}>{connection}</span>
        <span style={{ padding: '6px 10px', borderRadius: 999, border: '1px solid #ccd5e1', background: '#fff' }}>Hotkey: Ctrl/Command+Shift+Space</span>
      </div>
    </header>

    <div style={{ ...chrome, marginBottom: 10, display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 12 }}>
      <div>
        <strong>Current Context</strong>
        <div style={{ marginTop: 6 }}>{capturedContext?.active_app || 'Unknown app'}{capturedContext?.window_title ? ` / ${capturedContext.window_title}` : ''}</div>
        <div style={{ color: '#526173', overflowWrap: 'anywhere' }}>{currentUrl || capturedContext?.browser_url || capturedContext?.workspace_hint || 'No current URL or workspace yet'}</div>
      </div>
      <div>
        <strong>Run Timeline</strong>
        <div style={{ marginTop: 6 }}>Run: {runId || '-'} / Status: {runStatus} / Elapsed: {elapsed}s</div>
        <div style={{ color: '#526173' }}>Flow: {launchFlow} / Session: {sessionState}</div>
      </div>
    </div>

    {needsUser && <div role='alert' style={{ background: '#fff4db', border: '1px solid #f0c36d', padding: 12, borderRadius: 8, marginBottom: 10 }}>
      <strong>{pendingApproval ? 'Approval needed:' : 'Action needed:'}</strong> {pendingApproval ? approvalMessage : needsUser}{pendingRisk ? ` (${pendingRisk})` : ''}
      {!pendingApproval && <div style={{ marginTop: 8 }}><button onClick={async () => {
        const r = await resumeRun(runId);
        setOut(JSON.stringify(r, null, 2));
        await refreshRunState(runId);
      }}>Continue</button></div>}
    </div>}

    <div style={{ ...chrome, marginBottom: 10 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
      {QUICK_ACTIONS.map(action => <button key={action} title={`Set command: ${action}`} onClick={() => setInput(action)}>{action}</button>)}
      <button onClick={async () => setPreviewContext(await getCurrentContext())}>Refresh context</button>
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <input value={input} onChange={e => setInput(e.target.value)} placeholder={commandPlaceholder} style={{ flex: 1, minWidth: 260, padding: 10, border: '1px solid #c9d3df', borderRadius: 6 }} />
        <button onClick={() => run()}>Run</button>
        <button onClick={() => panicStop(runId)} disabled={!runId}>Panic Stop</button>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
        {!!clarifications.length && <button onClick={() => run(autoChoices)}>Answer Clarifications</button>}
        <button onClick={() => navigator.clipboard.writeText(finalText)}>Copy final answer</button>
        <button onClick={async () => {
      if (window.auraDesktop?.openLogs) setLogsPath(await window.auraDesktop.openLogs());
      else setLogsPath('No desktop bridge. Logs: system default location.');
        }}>Open logs folder</button>
        <button onClick={refreshKnowledge}>Refresh Panels</button>
      </div>
      {logsPath && <p>Logs: {logsPath}</p>}
    </div>

    <nav style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
      {PANELS.map(panel => <button key={panel} onClick={() => setActivePanel(panel)} style={activePanel === panel ? activeTabStyle : tabStyle}>{panel}</button>)}
    </nav>

    {activePanel === 'Run' && <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12, marginBottom: 12 }}>
      <section style={chrome}>
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

      <section style={chrome}>
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
    </div>}

    {activePanel === 'Run' && <ActionPanel events={events} />}

    {activePanel === 'Safety' && <section style={chrome}>
      <h3>Safety Cockpit</h3>
      <ul>{safety.slice(-20).map((s, i) => <li key={i}>{s.kind} / {s.action || s.step_id} / {s.ok === false ? 'fail' : 'ok'}</li>)}</ul>
    </section>}

    {activePanel === 'Workflows' && <section style={chrome}>
      <h3>Reusable Workflows</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div>
          <h4>Saved</h4>
          <ul>{workflows.map((workflow: any) => <li key={workflow.workflow_id}>
            <strong>{workflow.name}</strong> / {workflow.command_template}
            <button style={{ marginLeft: 8 }} onClick={async () => {
              const context = previewContext || await getCurrentContext().catch(() => null);
              const r = await runWorkflow(workflow.workflow_id, context);
              setOut(JSON.stringify(r, null, 2));
              if (r.run_id) {
                setRunId(r.run_id);
                setRunStatus(r.status || (r.ok ? 'done' : 'waiting'));
                await refreshRunState(r.run_id);
              }
            }}>Run</button>
          </li>)}</ul>
        </div>
        <div>
          <h4>Suggestions</h4>
          <ul>{workflowSuggestions.map((suggestion: any, index: number) => <li key={`${suggestion.task_type}-${suggestion.pattern_key}-${index}`}>
            <strong>{suggestion.suggested_workflow_name || suggestion.name}</strong>
            <div>{suggestion.command_template}</div>
            <button onClick={async () => {
              const created = await createWorkflow({
                name: suggestion.suggested_workflow_name || suggestion.name,
                description: suggestion.description || '',
                command_template: suggestion.command_template,
                trigger_type: suggestion.trigger_type || 'manual',
                trigger_value: suggestion.trigger_value || suggestion.pattern_key || '',
                source: suggestion.source || 'desktop_suggestion',
                confidence: suggestion.confidence || 0.5,
              });
              setOut(JSON.stringify(created, null, 2));
              await refreshKnowledge();
            }}>Save</button>
          </li>)}</ul>
        </div>
      </div>
    </section>}

    {activePanel === 'Memory' && <section style={chrome}>
      <h3>What AURA Knows</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
      <div><h4>Personal Memory</h4><ul>{memoryItems.slice(0,20).map((m: any) => <li key={m.memory_id}>{m.kind} / {m.memory_key}: {m.value}</li>)}</ul></div>
      <div><h4>Preferences</h4><ul>{prefs.map((p: any) => <li key={p.decision_key}>{p.decision_key}: {p.value} ({Math.round((p.confidence||0)*100)}%)</li>)}</ul></div>
      <div><h4>Memories</h4><ul>{memories.slice(0,20).map((m: any) => <li key={m.id}>{m.key}: {m.value}</li>)}</ul></div>
      <div><h4>Sessions</h4><ul>{sessions.map((s: any) => <li key={s.domain}>{s.domain}</li>)}</ul></div>
      <div><h4>Storage Stats</h4><pre>{JSON.stringify(storage, null, 2)}</pre></div>
      </div>
    </section>}

    {activePanel === 'System' && <section style={chrome}>
      <h3>Tool Registry</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 8 }}>
        {tools.slice(0, 18).map((tool: any) => <div key={tool.action_type} style={{ border: '1px solid #e0e6ef', borderRadius: 6, padding: 8 }}>
          <strong>{tool.action_type}</strong>
          <div>{tool.tool} / {tool.risk_level}{tool.requires_approval ? ' / approval' : ''}</div>
        </div>)}
      </div>
      <h3>Device Adapters</h3>
      <ul>{devices.map((device: any) => <li key={device.adapter_id}><strong>{device.name}</strong>: {device.surface} / {device.status}</li>)}</ul>
    </section>}

    <pre>{out}</pre>
  </div>;
}
