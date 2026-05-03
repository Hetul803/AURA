import { useEffect, useMemo, useRef, useState } from 'react';
import { approveRun, captureAssistContext, compactMemory, createWorkflow, getCostModels, getCostSummary, getCurrentContext, getDevices, getGuardianStatus, getLocalModelStatus, getMemoryItems, getProfileStatus, getRunState, getTools, getWorkflowSuggestions, getWorkflows, panicStop, pullLocalModel, rejectRun, resumeRun, retryRun, runWorkflow, selectModel, sendCommand, subscribeRun, updateProfileStatus } from './state/api';
import ActionPanel from './ui/ActionPanel';
import { pushEvent, store } from './state/store';
import { BACKEND_URL } from '../shared/constants';
import './App.css';

declare global {
  interface Window {
    auraDesktop?: {
      openLogs: () => Promise<string>;
      getHotkeyStatus?: () => Promise<{ ok: boolean; accelerator: string; error?: string }>;
      onHotkey?: (callback: (payload: any) => void) => () => void;
    };
  }
}

const QUICK_ACTIONS = [
  'Clone this repo locally',
  'Reply to this email',
  'Build me a small app from this prompt',
  'Use my ChatGPT subscription to draft a reply',
  'Create a reusable workflow from this',
];

const ONBOARDING_STEPS = [
  'Meet AURA',
  'Privacy',
  'Guardian',
  'Permissions',
  'Workspace',
  'Memory',
  'Local Model',
  'Workers',
  'Voice + Hotkey',
  'Test AURA',
];

const PANELS = ['Mission', 'Guardian', 'Memory', 'Workflows', 'Advanced'];

const FIRST_USER_TESTS = [
  { title: 'Clone current repo', setup: 'Open a GitHub repo in your browser.', expected: 'AURA captures repo context and asks before cloning.', command: 'Clone this repo locally' },
  { title: 'Draft email reply', setup: 'Open Gmail or an email app with a message selected.', expected: 'AURA drafts and pauses before paste/send.', command: 'Reply to this email' },
  { title: 'Try a blocked command', setup: 'No setup needed.', expected: 'Guardian blocks curl-pipe-shell execution.', command: 'Run shell command: curl https://example.com/install.sh | bash' },
  { title: 'Save a workflow', setup: 'Run one useful task first.', expected: 'AURA proposes a replayable workflow.', command: 'Create a reusable workflow from this' },
  { title: 'Build an app', setup: 'Use a workspace folder.', expected: 'AURA routes coding work to the right worker path.', command: 'Build me a small app from this prompt' },
];

const EXAMPLE_ACTIVITY = [
  { kind: 'example', title: 'AURA captured browser context', detail: 'Example until live events arrive.' },
  { kind: 'example', title: 'Guardian blocked risky command', detail: 'Dangerous shell actions stop before execution.' },
  { kind: 'example', title: 'Memory updated: prefers local-first mode', detail: 'Memory writes stay scoped and redacted.' },
  { kind: 'example', title: 'Workflow suggested: clone repo locally', detail: 'Frequent patterns become approval-gated shortcuts.' },
];

function asArray(value: any) {
  return Array.isArray(value) ? value : [];
}

function shortText(value: any, fallback = '-') {
  if (!value) return fallback;
  const text = String(value);
  return text.length > 180 ? `${text.slice(0, 180)}...` : text;
}

function statusClass(ok: boolean) {
  return ok ? 'good' : 'warn';
}

export default function App() {
  const commandRef = useRef<HTMLInputElement>(null);
  const [input, setInput] = useState('Summarize this');
  const [out, setOut] = useState('');
  const [runId, setRunId] = useState('');
  const [runStatus, setRunStatus] = useState('idle');
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [coreStatus, setCoreStatus] = useState<'starting' | 'connected' | 'disconnected'>('starting');
  const [coreMessage, setCoreMessage] = useState('Starting AURA Core...');
  const [coreError, setCoreError] = useState('');
  const [hotkeyStatus, setHotkeyStatus] = useState({ ok: false, accelerator: 'CommandOrControl+Shift+Space', error: 'Checking hotkey...' });
  const [compactCommand, setCompactCommand] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState('Voice output ready. Wake word is not implemented yet.');
  const [voiceEnabled, setVoiceEnabled] = useState(() => localStorage.getItem('aura:voice-enabled') === '1');
  const [contextStatus, setContextStatus] = useState('AURA is checking what it can see.');
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
  const [activePanel, setActivePanel] = useState('Mission');
  const [onboardingOpen, setOnboardingOpen] = useState(() => localStorage.getItem('aura:onboarding-complete') !== '1');
  const [onboardingStep, setOnboardingStep] = useState(() => Number(localStorage.getItem('aura:onboarding-step') || '0'));
  const [onboardingPrefs, setOnboardingPrefs] = useState({ memoryScope: 'personal', approvalMode: 'balanced', monthlyBudget: '0', workspace: '', selectedLocalModel: '', codexBridge: false, userAiHandoff: true, localModelSkipped: false });
  const [modelPullState, setModelPullState] = useState('');
  const [modelError, setModelError] = useState('');

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
  const [profileStatus, setProfileStatus] = useState<any>(null);
  const [guardianStatus, setGuardianStatus] = useState<any>(null);
  const [costSummary, setCostSummary] = useState<any>(null);
  const [costModels, setCostModels] = useState<any[]>([]);
  const [localModelStatus, setLocalModelStatus] = useState<any>(null);

  async function refreshConnection() {
    setCoreStatus((current) => current === 'connected' ? current : 'starting');
    setCoreMessage('Starting AURA Core...');
    try {
      const r = await fetch(`${BACKEND_URL}/health`);
      if (!r.ok) throw new Error(`Health check returned HTTP ${r.status}`);
      setCoreStatus('connected');
      setCoreMessage('AURA Core online.');
      setCoreError('');
      return true;
    } catch (error: any) {
      setCoreStatus('disconnected');
      setCoreMessage('AURA Core disconnected.');
      setCoreError(error?.message || `Cannot reach ${BACKEND_URL}`);
      return false;
    }
  }

  async function safeJson<T>(loader: () => Promise<T>, fallback: T) {
    try {
      return await loader();
    } catch {
      return fallback;
    }
  }

  async function refreshKnowledge() {
    const [p, m, ss, st, se, ts, ds, mi, wf, ws, profile, guardian, cost, models, localModel] = await Promise.all([
      safeJson(() => fetch(`${BACKEND_URL}/preferences`).then(r => r.json()), []),
      safeJson(() => fetch(`${BACKEND_URL}/memories`).then(r => r.json()), []),
      safeJson(() => fetch(`${BACKEND_URL}/browser/sessions`).then(r => r.json()), []),
      safeJson(() => fetch(`${BACKEND_URL}/storage/stats`).then(r => r.json()), {}),
      safeJson(() => fetch(`${BACKEND_URL}/safety/events`).then(r => r.json()), []),
      safeJson(() => getTools(), []),
      safeJson(() => getDevices(), []),
      safeJson(() => getMemoryItems(), []),
      safeJson(() => getWorkflows(), []),
      safeJson(() => getWorkflowSuggestions(), []),
      safeJson(() => getProfileStatus(), null),
      safeJson(() => getGuardianStatus(runId || undefined), null),
      safeJson(() => getCostSummary(), null),
      safeJson(() => getCostModels(), []),
      safeJson(() => getLocalModelStatus(), null),
    ]);
    setPrefs(asArray(p)); setMemories(asArray(m)); setSessions(asArray(ss)); setStorage(st || {}); setSafety(asArray(se));
    setTools(asArray(ts)); setDevices(asArray(ds)); setMemoryItems(asArray(mi)); setWorkflows(asArray(wf));
    setWorkflowSuggestions(asArray(ws)); setProfileStatus(profile); setGuardianStatus(guardian); setCostSummary(cost);
    setCostModels(asArray(models));
    if (localModel) {
      setLocalModelStatus(localModel);
      setModelError('');
    } else {
      setModelError('Local model detection API did not respond. Start the backend and retry.');
    }
  }

  async function refreshContext() {
    setContextStatus('Capturing current app, window, browser, and selection...');
    try {
      const context = await getCurrentContext();
      setPreviewContext(context);
      setContextStatus(context?.active_app || context?.input_text ? 'AURA refreshed current context.' : 'Context refresh returned no visible app data. Check Accessibility and Screen Recording permissions.');
    } catch (error: any) {
      try {
        const context = await captureAssistContext();
        setPreviewContext(context);
        setContextStatus('AURA captured fallback clipboard/assist context.');
      } catch {
        setContextStatus(`Context unavailable: ${error?.message || 'permission or backend issue'}. Enable Accessibility/Screen Recording, then retry.`);
      }
    }
  }

  async function refreshRunState(targetRunId = runId) {
    if (!targetRunId) return;
    try {
      const state = await getRunState(targetRunId);
      setRunState(state);
      setDraftText(state?.approval_state?.edited_text || state?.approval_state?.draft_text || state?.draft_state?.draft_text || '');
    } catch {
      setRunStatus('disconnected');
    }
  }

  function speak(text: string) {
    if (!('speechSynthesis' in window)) {
      setVoiceStatus('Speech synthesis is unavailable in this renderer.');
      return;
    }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    setVoiceStatus('AURA is speaking.');
  }

  async function pushToTalk() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setVoiceStatus('Microphone capture is unavailable. Voice input coming soon on this build.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      setVoiceStatus('Microphone permission granted. Live speech recognition and Hey AURA wake word are not implemented yet.');
    } catch (error: any) {
      setVoiceStatus(`Microphone unavailable: ${error?.message || 'permission denied'}.`);
    }
  }

  useEffect(() => {
    let alive = true;
    let delay = 500;
    async function tick() {
      const ok = await refreshConnection();
      if (!alive) return;
      delay = ok ? 2000 : Math.min(delay * 2, 7000);
      setTimeout(tick, delay);
    }
    tick();
    refreshKnowledge();
    refreshContext();
    window.auraDesktop?.getHotkeyStatus?.().then(setHotkeyStatus).catch(() => undefined);
    const unsubscribe = window.auraDesktop?.onHotkey?.(() => {
      setCompactCommand(true);
      setOnboardingOpen(false);
      setTimeout(() => commandRef.current?.focus(), 0);
    });
    return () => { alive = false; unsubscribe?.(); };
  }, []);

  useEffect(() => {
    localStorage.setItem('aura:onboarding-step', String(onboardingStep));
  }, [onboardingStep]);

  useEffect(() => {
    localStorage.setItem('aura:voice-enabled', voiceEnabled ? '1' : '0');
  }, [voiceEnabled]);

  useEffect(() => {
    if (!startedAt) return;
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 200);
    return () => clearInterval(t);
  }, [startedAt]);

  async function run(choices: Record<string, string> = {}, useMacro = false) {
    const context = previewContext || await getCurrentContext().catch(() => null);
    if (context) setPreviewContext(context);
    setRunStatus('thinking');
    setNeedsUser('');
    const res = await sendCommand(input, choices, useMacro, context);
    setOut(JSON.stringify(res, null, 2));
    setRunStatus(res.status || (res.ok ? 'running' : 'waiting'));
    if (voiceEnabled) speak('I am working on it. Guardian will pause anything risky.');
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
        if (evt.type === 'guardian_event') setGuardianStatus(await getGuardianStatus(res.run_id));
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
  const pasteState = runState?.pasteback_state || {};
  const pendingRisk = approvalState.risk_reason || approvalState.action_type || '';
  const launchFlow = runState?.plan?.signature || (capturedContext?.browser_url?.includes('github.com') ? 'github:clone' : 'desktop');
  const recommendedModel = localModelStatus?.recommendation?.recommended_pull || localModelStatus?.recommendation?.model || 'gemma4:e4b-nvfp4';
  const selectedLocalModel = onboardingPrefs.selectedLocalModel || recommendedModel;
  const selectedModelId = localModelStatus?.selected_model?.id || localModelStatus?.selected_model?.model;
  const localReady = Boolean((localModelStatus?.selected_model?.available && selectedModelId !== 'simple') || localModelStatus?.runtime_ready || localModelStatus?.assist_drafting_ready);
  const guardianEvents = asArray(guardianStatus?.events);
  const liveActivity = events.length
    ? events.slice(-8).reverse().map((event) => ({ kind: event.type || event.status || 'run', title: event.message || event.type || 'AURA updated run state', detail: event.status || runId }))
    : EXAMPLE_ACTIVITY;
  const memoryFeed = [
    ...memoryItems.slice(0, 3).map((item: any) => ({ title: `Remembered: ${item.memory_key || item.kind || 'memory'}`, detail: shortText(item.value || item.summary || item.scope, 'Scoped memory item') })),
    ...prefs.slice(0, 2).map((item: any) => ({ title: `Learning: ${item.decision_key}`, detail: shortText(item.value, 'Preference signal') })),
  ];
  const blockedCount = safety.filter((item: any) => item.ok === false || item.decision === 'blocked' || item.status === 'blocked').length + guardianEvents.filter((item: any) => item.status === 'blocked' || item.decision === 'blocked').length;
  const approvalsHandled = Number(profileStatus?.stats?.approvals_handled || 0) + (pendingApproval ? 1 : 0);
  const workflowsReplayed = workflows.reduce((sum: number, wf: any) => sum + (wf.success_count || 0), 0);
  const conservativeMinutesSaved = Math.max(0, Math.min(240, events.length * 2 + workflowsReplayed * 4 + memoryItems.length));

  async function completeOnboarding() {
    localStorage.setItem('aura:onboarding-complete', '1');
    const metadata = { ...(profileStatus?.metadata || {}), onboarding: { completed: true, ...onboardingPrefs, local_model_status: localModelStatus?.summary, voice_enabled: voiceEnabled } };
    const usage_limits = onboardingPrefs.monthlyBudget ? { monthly_budget_usd: Number(onboardingPrefs.monthlyBudget) || 0 } : undefined;
    const updated = await updateProfileStatus({ metadata, usage_limits });
    setProfileStatus(updated);
    setOnboardingOpen(false);
    if (voiceEnabled) speak('Setup saved. Guardian is active. AURA Core is ready when connected.');
  }

  async function approveAndPullLocalModel() {
    setModelPullState(`Pulling ${selectedLocalModel}. This may take a while...`);
    const result = await pullLocalModel(selectedLocalModel, true);
    setModelPullState(result.ok ? `Pulled and selected ${selectedLocalModel}.` : JSON.stringify(result, null, 2));
    await refreshKnowledge();
  }

  async function useExistingOrSkipLocalModel(modelId?: string) {
    const target = modelId || (localModelStatus?.selected_model?.available ? `ollama:${localModelStatus.selected_model.model}` : 'simple');
    const result = await selectModel(target);
    setModelPullState(`Selected ${result.model_id}.`);
    setOnboardingPrefs({ ...onboardingPrefs, localModelSkipped: target === 'simple' });
    await refreshKnowledge();
  }

  function chooseCommand(command: string) {
    setInput(command);
    setCompactCommand(true);
    setTimeout(() => commandRef.current?.focus(), 0);
  }

  function onboardingCopy(step: string) {
    if (step === 'Meet AURA') return { title: 'I am AURA, your personal AI operating layer.', body: 'I help you use your computer safely: capture context, plan actions, draft work, route heavy tasks, and pause before anything risky.', does: 'Creates a live command center instead of a chatbot box.', why: 'You should know what I see, what I am doing, and what Guardian is protecting.' };
    if (step === 'Privacy') return { title: 'Local-first is the default.', body: 'Your profile, memory, workflows, and settings stay on this Mac unless you later opt into sync.', does: 'Keeps memory scoped to personal, work, company, session, or device.', why: 'AURA should feel powerful without casually leaking your life or work.' };
    if (step === 'Guardian') return { title: 'AURA does the work. Guardian protects you.', body: 'Guardian blocks destructive actions, redacts secrets, and requires approval for paste, send, shell, files, model spend, imports, exports, and risky replay.', does: 'Shows protection state and why an action needs approval.', why: 'Trust needs to be visible, not hidden in logs.' };
    if (step === 'Permissions') return { title: 'Permissions are explicit.', body: 'Accessibility helps AURA control apps. Screen Recording helps visual context. Automation may be requested by macOS per app.', does: 'Lets AURA capture context and bring the overlay forward.', why: 'Without permissions, AURA can still run, but computer control is limited.' };
    if (step === 'Workspace') return { title: 'Choose the workspace AURA can use.', body: 'Clones, builds, generated apps, and working files should stay in one user-approved folder.', does: 'Keeps file operations contained.', why: 'A clear workspace makes automation safer and easier to inspect.' };
    if (step === 'Memory') return { title: 'Choose how AURA remembers.', body: 'Start conservative. You can archive, delete, compact, export, or change scope later.', does: 'Stores useful preferences without secrets.', why: 'Memory is the user puller, but only if it earns trust.' };
    if (step === 'Local Model') return { title: 'Local model setup is optional and guided.', body: 'AURA detects hardware, Ollama, available models, and recommends a Gemma model only when appropriate.', does: 'Uses local models for private/cheap planning, routing, cleanup, drafts, and summaries.', why: 'Cloud AI should not be required just to start.' };
    if (step === 'Workers') return { title: 'Heavy workers stay optional.', body: 'Codex is for code implementation. ChatGPT and Claude browser handoff are explicit user choices.', does: 'Routes work by privacy, cost, and capability.', why: 'Local is not always best; silent cloud is not okay either.' };
    if (step === 'Voice + Hotkey') return { title: 'Voice and hotkey are control surfaces.', body: 'Command/Control+Shift+Space brings AURA forward. Speech output works where browser speech synthesis is available. Hey AURA wake word is not implemented yet.', does: 'Lets you test push-to-talk permission and spoken guidance honestly.', why: 'No fake wake word claims; the app should tell the truth.' };
    return { title: 'Test AURA like a first user.', body: 'Use guided cards to try repo clone, email draft, blocked command, workflow save, and app build flows.', does: 'Shows setup needed and expected result before each test.', why: 'Manual testing should feel guided, not like spelunking backend APIs.' };
  }

  function renderOnboarding() {
    const step = ONBOARDING_STEPS[onboardingStep] || ONBOARDING_STEPS[0];
    const copy = onboardingCopy(step);
    return <section className="onboarding-shell" aria-label="First-Time Setup">
      <div className="onboarding-hero">
        <div>
          <div className="eyebrow">First-Time Setup</div>
          <h2>{copy.title}</h2>
          <p>{copy.body}</p>
        </div>
        <button className="ghost-button" onClick={() => setOnboardingOpen(false)}>Later</button>
      </div>
      <div className="step-rail">
        {ONBOARDING_STEPS.map((item, index) => <button key={item} className={index === onboardingStep ? 'step active' : 'step'} onClick={() => setOnboardingStep(index)}>{index + 1}. {item}</button>)}
      </div>
      <div className="onboarding-grid">
        <div className="glass-panel">
          <div className="eyebrow">What AURA will do</div>
          <p>{copy.does}</p>
        </div>
        <div className="glass-panel">
          <div className="eyebrow">Why it matters</div>
          <p>{copy.why}</p>
        </div>
      </div>
      {step === 'Local Model' && <ModelStatusPanel localModelStatus={localModelStatus} modelError={modelError} selectedLocalModel={selectedLocalModel} setSelected={(value) => setOnboardingPrefs({ ...onboardingPrefs, selectedLocalModel: value })} approveAndPullLocalModel={approveAndPullLocalModel} skip={() => useExistingOrSkipLocalModel('simple')} refresh={refreshKnowledge} modelPullState={modelPullState} />}
      {step === 'Permissions' && <div className="callout"><strong>Current context check:</strong> {contextStatus}<div><button onClick={refreshContext}>Refresh context</button></div></div>}
      {step === 'Workspace' && <input className="wide-input" value={onboardingPrefs.workspace} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, workspace: e.target.value })} placeholder="/Users/you/Projects/AURA-workspace" />}
      {step === 'Memory' && <div className="settings-row"><label>Memory scope<select value={onboardingPrefs.memoryScope} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, memoryScope: e.target.value })}><option>personal</option><option>work</option><option>company</option><option>session</option><option>device</option></select></label><label>Approval mode<select value={onboardingPrefs.approvalMode} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, approvalMode: e.target.value })}><option>balanced</option><option>strict</option><option>demo</option></select></label><label>Monthly AI budget<input value={onboardingPrefs.monthlyBudget} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, monthlyBudget: e.target.value })} placeholder="0" /></label></div>}
      {step === 'Workers' && <div className="settings-row"><label><input type="checkbox" checked={onboardingPrefs.codexBridge} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, codexBridge: e.target.checked })} /> Optional Codex bridge</label><label><input type="checkbox" checked={onboardingPrefs.userAiHandoff} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, userAiHandoff: e.target.checked })} /> Optional ChatGPT/Claude handoff</label></div>}
      {step === 'Voice + Hotkey' && <VoiceHotkeyPanel voiceStatus={voiceStatus} voiceEnabled={voiceEnabled} setVoiceEnabled={setVoiceEnabled} speak={speak} pushToTalk={pushToTalk} hotkeyStatus={hotkeyStatus} />}
      {step === 'Test AURA' && <TestAuraCards chooseCommand={chooseCommand} localReady={localReady} coreOnline={coreStatus === 'connected'} />}
      <div className="onboarding-actions">
        <button onClick={() => setOnboardingStep(Math.max(0, onboardingStep - 1))} disabled={onboardingStep === 0}>Back</button>
        <button onClick={() => setOnboardingStep(Math.min(ONBOARDING_STEPS.length - 1, onboardingStep + 1))} disabled={onboardingStep === ONBOARDING_STEPS.length - 1}>Continue</button>
        <button className="primary-button" onClick={completeOnboarding}>Finish and save local profile</button>
        <button onClick={() => speak(copy.body)}>Speak guidance</button>
      </div>
    </section>;
  }

  return <div className={compactCommand ? 'app-shell compact-mode' : 'app-shell'}>
    <header className="topbar">
      <div>
        <div className="brand-row"><span className="brand-mark">A</span><span>AURA</span></div>
        <p>Personal AI operating layer. AURA does the work; Guardian protects you.</p>
      </div>
      <div className="status-cluster">
        <StatusPill label={coreStatus === 'connected' ? 'AURA Core online' : coreStatus === 'starting' ? 'Starting AURA Core...' : 'AURA Core disconnected'} tone={coreStatus === 'connected' ? 'good' : coreStatus === 'starting' ? 'warn' : 'bad'} />
        <StatusPill label={`Guardian: ${guardianStatus?.status || 'Protected'}`} tone="good" />
        <StatusPill label={hotkeyStatus.ok ? 'Hotkey active' : 'Hotkey unavailable'} tone={hotkeyStatus.ok ? 'good' : 'bad'} />
        <StatusPill label={localReady ? 'Local model ready' : 'Local model setup'} tone={localReady ? 'good' : 'warn'} />
        <StatusPill label="Local-first mode" tone="privacy" />
      </div>
    </header>

    {onboardingOpen && renderOnboarding()}

    <section className="hero-command">
      <div className="orbital-status">
        <div className="pulse-ring"><span /></div>
        <div>
          <div className="eyebrow">Mission Control</div>
          <h1>What should AURA do?</h1>
          <p>{coreMessage}{coreError ? ` ${coreError}` : ''}</p>
        </div>
      </div>
      <div className="command-bar">
        <button className="voice-button" onClick={pushToTalk} title="Push to talk">Voice</button>
        <input ref={commandRef} aria-label="command input" value={input} onChange={e => setInput(e.target.value)} placeholder="Ask AURA to act on the current app, page, repo, or selection" />
        <button className="primary-button" aria-label="run command" onClick={() => run()}>Run</button>
      </div>
      <div className="suggestions">
        {QUICK_ACTIONS.map(action => <button key={action} onClick={() => chooseCommand(action)}>{action}</button>)}
      </div>
      <div className="micro-status">
        <span>{voiceStatus}</span>
        <span>{hotkeyStatus.ok ? `${hotkeyStatus.accelerator} brings AURA forward.` : `${hotkeyStatus.error || 'Enable Accessibility permission if macOS blocks the shortcut.'}`}</span>
      </div>
    </section>

    {coreStatus !== 'connected' && <div role="alert" className="repair-banner">
      <strong>{coreMessage}</strong>
      <span>{coreError || `Waiting for ${BACKEND_URL}`}</span>
      <button onClick={async () => { await refreshConnection(); await refreshKnowledge(); }}>Repair / retry</button>
      <button onClick={async () => setLogsPath(window.auraDesktop?.openLogs ? await window.auraDesktop.openLogs() : 'No desktop bridge. Start from Electron for logs.')}>Open logs</button>
    </div>}

    {needsUser && <div role="alert" className="approval-banner">
      <strong>{pendingApproval ? 'Approval required' : 'Action needed'}</strong>
      <span>{pendingApproval ? (toolApproval ? `Approve ${approvalState.step_name || approvalState.action_type || 'this action'}` : 'Review the draft, edit if needed, then approve paste-back.') : needsUser}{pendingRisk ? ` (${pendingRisk})` : ''}</span>
      {!pendingApproval && <button onClick={async () => { const r = await resumeRun(runId); setOut(JSON.stringify(r, null, 2)); await refreshRunState(runId); }}>Continue</button>}
    </div>}

    <main className="dashboard-grid">
      <section className="glass-panel context-panel">
        <PanelTitle eyebrow="AURA sees" title={capturedContext?.active_app || 'Unknown app'} />
        <div className="context-lines">
          <div><span>Window</span>{capturedContext?.window_title || '-'}</div>
          <div><span>URL</span>{shortText(currentUrl || capturedContext?.browser_url, 'No browser URL yet')}</div>
          <div><span>Workspace</span>{capturedContext?.workspace_hint || capturedContext?.project?.current_folder || '-'}</div>
          <div><span>Selection</span>{shortText(capturedContext?.input_text, 'No selected text captured')}</div>
        </div>
        <div className="panel-actions">
          <button onClick={refreshContext}>Refresh context</button>
          <button onClick={() => { setOnboardingStep(3); setOnboardingOpen(true); }}>Permission help</button>
        </div>
        <p className="helper-text">{contextStatus}</p>
      </section>

      <section className="glass-panel guardian-card">
        <PanelTitle eyebrow="AURA Guardian" title={guardianStatus?.status || 'Protected'} />
        <div className="guardian-core">Protected</div>
        <p>Approval required for paste/send, risky shell, workflow replay, imports, exports, memory export, and paid actions.</p>
        <div className="guardian-grid">
          <span>Watching for secrets</span>
          <span>Secret redaction active</span>
          <span>Shell/file policy active</span>
          <span>Local-first mode active</span>
        </div>
        <button className="danger-button" onClick={() => panicStop(runId)} disabled={!runId}>Panic Stop</button>
      </section>

      <section className="glass-panel activity-panel">
        <PanelTitle eyebrow="Live activity" title={events.length ? 'AURA is working' : 'Examples until live events arrive'} />
        <Feed items={liveActivity} />
      </section>

      <section className="glass-panel savings-panel">
        <PanelTitle eyebrow="Time saved / work handled" title={`${conservativeMinutesSaved} min estimated`} />
        <div className="metric-grid">
          <Metric label="Runs" value={events.length || 0} />
          <Metric label="Approvals" value={approvalsHandled} />
          <Metric label="Workflows" value={workflowsReplayed} />
          <Metric label="Blocked" value={blockedCount} />
        </div>
        <p className="helper-text">Conservative estimate from completed run events, replayed workflows, and useful memory signals.</p>
      </section>
    </main>

    <nav className="panel-tabs">
      {PANELS.map(panel => <button key={panel} className={activePanel === panel ? 'active' : ''} onClick={() => setActivePanel(panel)}>{panel}</button>)}
    </nav>

    {activePanel === 'Mission' && <section className="panel-body">
      <TestAuraCards chooseCommand={chooseCommand} localReady={localReady} coreOnline={coreStatus === 'connected'} />
      <DraftReview runId={runId} pendingApproval={pendingApproval} toolApproval={toolApproval} approvalState={approvalState} generation={generation} pasteState={pasteState} draftText={draftText} setDraftText={setDraftText} feedback={feedback} setFeedback={setFeedback} approve={async () => { const r = await approveRun(runId, draftText); setOut(JSON.stringify(r, null, 2)); await refreshRunState(runId); }} retry={async () => { const r = await retryRun(runId, feedback); setOut(JSON.stringify(r, null, 2)); await refreshRunState(runId); }} reject={async () => { const r = await rejectRun(runId, feedback); setOut(JSON.stringify(r, null, 2)); await refreshRunState(runId); }} />
    </section>}

    {activePanel === 'Guardian' && <section className="panel-body">
      <GuardianPanel guardianStatus={guardianStatus} safety={safety} runId={runId} panic={() => panicStop(runId)} />
    </section>}

    {activePanel === 'Memory' && <section className="panel-body two-column">
      <div className="glass-panel"><PanelTitle eyebrow="Memory intelligence" title="Useful learning" /><Feed items={memoryFeed.length ? memoryFeed : [{ kind: 'empty', title: 'No memory updates yet', detail: 'AURA will show useful learning here after real tasks.' }]} /><button onClick={async () => { const r = await compactMemory('personal'); setOut(JSON.stringify(r, null, 2)); await refreshKnowledge(); }}>Compact personal memory</button></div>
      <div className="glass-panel"><PanelTitle eyebrow="Local model" title={localReady ? 'Ready' : 'Needs setup'} /><ModelStatusPanel localModelStatus={localModelStatus} modelError={modelError} selectedLocalModel={selectedLocalModel} setSelected={(value) => setOnboardingPrefs({ ...onboardingPrefs, selectedLocalModel: value })} approveAndPullLocalModel={approveAndPullLocalModel} skip={() => useExistingOrSkipLocalModel('simple')} refresh={refreshKnowledge} modelPullState={modelPullState} /></div>
    </section>}

    {activePanel === 'Workflows' && <section className="panel-body two-column">
      <div className="glass-panel"><PanelTitle eyebrow="Saved workflows" title={`${workflows.length} ready`} />{workflows.length ? workflows.map((workflow: any) => <div className="flow-row" key={workflow.workflow_id}><strong>{workflow.name}</strong><span>{workflow.command_template}</span><button onClick={async () => { const r = await runWorkflow(workflow.workflow_id, previewContext); setOut(JSON.stringify(r, null, 2)); if (r.run_id) { setRunId(r.run_id); await refreshRunState(r.run_id); } }}>Run</button></div>) : <p>No saved workflows yet.</p>}</div>
      <div className="glass-panel"><PanelTitle eyebrow="Workflow intelligence" title="Suggestions" />{workflowSuggestions.length ? workflowSuggestions.map((suggestion: any, index: number) => <div className="flow-row" key={`${suggestion.task_type}-${index}`}><strong>{suggestion.suggested_workflow_name || suggestion.name}</strong><span>{suggestion.command_template}</span><button onClick={async () => { const created = await createWorkflow({ name: suggestion.suggested_workflow_name || suggestion.name, description: suggestion.description || '', command_template: suggestion.command_template, trigger_type: suggestion.trigger_type || 'manual', trigger_value: suggestion.trigger_value || suggestion.pattern_key || '', source: suggestion.source || 'desktop_suggestion', confidence: suggestion.confidence || 0.5 }); setOut(JSON.stringify(created, null, 2)); await refreshKnowledge(); }}>Save</button></div>) : <p>AURA will suggest workflows after repeated useful actions.</p>}</div>
    </section>}

    {activePanel === 'Advanced' && <section className="panel-body">
      <details className="glass-panel"><summary>Raw run timeline</summary><ActionPanel events={events} /></details>
      <details className="glass-panel"><summary>Raw context JSON</summary><pre>{JSON.stringify(capturedContext, null, 2)}</pre></details>
      <details className="glass-panel"><summary>System, model, and backend internals</summary><p>Backend: {BACKEND_URL} / {coreStatus} / Flow: {launchFlow} / Session: {sessionState}</p><p>Logs: {logsPath || '-'}</p><button onClick={async () => setLogsPath(window.auraDesktop?.openLogs ? await window.auraDesktop.openLogs() : 'No desktop bridge.')}>Open logs folder</button><pre>{JSON.stringify({ profileStatus, costSummary, costModels, tools, devices, sessions, storage, out }, null, 2)}</pre></details>
    </section>}

    <footer className="footer-line">AURA Core: {coreStatus}. Guardian: protected. Wake word: not implemented yet. Voice output: {voiceEnabled ? 'enabled' : 'optional'}.</footer>
  </div>;
}

function StatusPill(props: { label: string; tone: string }) {
  return <span className={`status-pill ${props.tone}`}>{props.label}</span>;
}

function PanelTitle(props: { eyebrow: string; title: string }) {
  return <div className="panel-title"><span>{props.eyebrow}</span><h2>{props.title}</h2></div>;
}

function Metric(props: { label: string; value: any }) {
  return <div className="metric"><strong>{props.value}</strong><span>{props.label}</span></div>;
}

function Feed(props: { items: Array<{ kind?: string; title: string; detail?: string }> }) {
  return <div className="feed-list">{props.items.map((item, index) => <div className={`feed-item ${item.kind || ''}`} key={`${item.title}-${index}`}><div className="feed-dot" /><div><strong>{item.title}</strong><p>{item.detail}</p></div></div>)}</div>;
}

function ModelStatusPanel(props: { localModelStatus: any; modelError: string; selectedLocalModel: string; setSelected: (value: string) => void; approveAndPullLocalModel: () => void; skip: () => void; refresh: () => void; modelPullState: string }) {
  const hw = props.localModelStatus?.hardware || {};
  const ollama = props.localModelStatus?.ollama || {};
  const recommendation = props.localModelStatus?.recommendation || {};
  return <div className="model-grid">
    {props.modelError && <div className="callout bad">{props.modelError}</div>}
    <div className="glass-panel"><span>OS</span><strong>{hw.os || 'Unknown'}</strong></div>
    <div className="glass-panel"><span>Chip</span><strong>{hw.apple_silicon ? 'Apple Silicon' : hw.arch === 'x64' ? 'Intel' : hw.arch || 'Unknown'}</strong></div>
    <div className="glass-panel"><span>RAM</span><strong>{hw.ram_gb ? `${hw.ram_gb} GB` : 'Unknown'}</strong></div>
    <div className="glass-panel"><span>Ollama</span><strong>{ollama.installed ? 'Installed' : 'Missing'} / {ollama.running ? 'Running' : 'Stopped'}</strong></div>
    <div className="glass-panel wide"><span>Recommended local model</span><strong>{recommendation.model || props.selectedLocalModel}</strong><p>{recommendation.reason || 'AURA recommends a small private model until hardware detection completes.'}</p></div>
    <div className="glass-panel wide"><span>Local model status</span><strong>{props.localModelStatus?.summary || 'Checking local model runtime...'}</strong><input aria-label="local model name" value={props.selectedLocalModel} onChange={e => props.setSelected(e.target.value)} /><div className="panel-actions"><button onClick={props.approveAndPullLocalModel} disabled={!ollama.installed}>Approve Pull Model</button><button onClick={props.skip}>Skip for now</button><button onClick={props.refresh}>Refresh</button></div>{props.modelPullState && <pre>{props.modelPullState}</pre>}</div>
  </div>;
}

function VoiceHotkeyPanel(props: { voiceStatus: string; voiceEnabled: boolean; setVoiceEnabled: (value: boolean) => void; speak: (text: string) => void; pushToTalk: () => void; hotkeyStatus: { ok: boolean; accelerator: string; error?: string } }) {
  return <div className="voice-grid">
    <div className="glass-panel"><span>Hotkey</span><strong>{props.hotkeyStatus.ok ? 'Hotkey active' : 'Hotkey unavailable'}</strong><p>{props.hotkeyStatus.ok ? `${props.hotkeyStatus.accelerator} opens compact command mode.` : `${props.hotkeyStatus.error || 'Enable Accessibility permission if macOS blocks it.'}`}</p></div>
    <div className="glass-panel"><span>Voice output</span><strong>{props.voiceEnabled ? 'Enabled' : 'Optional'}</strong><label><input type="checkbox" checked={props.voiceEnabled} onChange={e => props.setVoiceEnabled(e.target.checked)} /> Speak guidance and status</label><button onClick={() => props.speak("I'm AURA. I help you use your computer safely. Guardian is active.")}>Speak intro</button></div>
    <div className="glass-panel"><span>Voice input</span><strong>Push-to-talk foundation</strong><p>{props.voiceStatus}</p><button onClick={props.pushToTalk}>Test microphone</button><p className="helper-text">Hey AURA wake word is not implemented yet.</p></div>
  </div>;
}

function TestAuraCards(props: { chooseCommand: (command: string) => void; localReady: boolean; coreOnline: boolean }) {
  return <div className="launch-grid">{FIRST_USER_TESTS.map((card) => <article className="launch-card" key={card.title}><span>{props.coreOnline ? 'Ready when context is available' : 'Core must connect first'}</span><h3>{card.title}</h3><p><strong>Setup:</strong> {card.setup}</p><p><strong>Expected:</strong> {card.expected}</p><p><strong>Local model:</strong> {props.localReady ? 'ready' : 'optional / fallback'}</p><button onClick={() => props.chooseCommand(card.command)}>Start</button></article>)}</div>;
}

function DraftReview(props: any) {
  return <div className="glass-panel draft-panel">
    <PanelTitle eyebrow="AURA is thinking" title={props.pendingApproval ? 'Approval required' : 'Draft review'} />
    <div className="context-lines">
      <div><span>Run</span>{props.runId || '-'}</div>
      <div><span>Approval</span>{props.approvalState.status || 'not requested'}</div>
      <div><span>Generation</span>{props.generation.provider ? `${props.generation.provider}${props.generation.model ? ` / ${props.generation.model}` : ''}` : '-'}</div>
      <div><span>Paste validation</span>{props.pasteState.target_validation_result || props.pasteState.target_validation || '-'}</div>
    </div>
    {!props.toolApproval && <textarea aria-label="draft editor" value={props.draftText} onChange={(e) => props.setDraftText(e.target.value)} rows={7} placeholder="Generated draft will appear here." />}
    {props.toolApproval && <pre>{JSON.stringify(props.approvalState.requested_args || {}, null, 2)}</pre>}
    <input aria-label="retry feedback" value={props.feedback} onChange={(e) => props.setFeedback(e.target.value)} placeholder="Optional retry feedback" />
    <div className="panel-actions"><button disabled={!props.runId || !props.pendingApproval} onClick={props.approve}>{props.toolApproval ? 'Approve Action' : 'Approve & Paste'}</button><button disabled={!props.runId || !props.pendingApproval || props.toolApproval} onClick={props.retry}>Retry</button><button disabled={!props.runId || !props.pendingApproval} onClick={props.reject}>Reject</button></div>
  </div>;
}

function GuardianPanel(props: { guardianStatus: any; safety: any[]; runId: string; panic: () => void }) {
  const events = asArray(props.guardianStatus?.events);
  return <div className="guardian-detail-grid">
    <div className="glass-panel"><PanelTitle eyebrow="Protection level" title="Protected" /><p>{props.guardianStatus?.summary || 'Guardian is watching for secrets, risky actions, unsafe paste/send, shell/file risk, and workflow replay risk.'}</p><div className="guardian-grid"><span>Approval required</span><span>Blocked by default</span><span>Watching for secrets</span><span>Local-first mode active</span><span>Paste/send policy active</span><span>Shell/file risk policy active</span></div><button className="danger-button" onClick={props.panic} disabled={!props.runId}>Panic Stop</button></div>
    <div className="glass-panel"><PanelTitle eyebrow="Recent blocked/actions" title={`${events.length + props.safety.length} signals`} /><Feed items={(events.length ? events : props.safety.slice(-8)).map((event: any) => ({ title: event.summary || event.message || event.kind || event.type || 'Guardian event', detail: event.explanation || event.action || event.step_id || event.risk || 'Protection state updated.' }))} /></div>
  </div>;
}
