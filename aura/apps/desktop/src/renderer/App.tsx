import { useEffect, useMemo, useRef, useState } from 'react';
import { approveRun, captureAssistContext, getAssistPersonalization, getDemoStatus, getGuardianEvents, getModelStatus, getProactiveSuggestions, getRunState, healthcheck, panicStop, rejectRun, resumeRun, retryRun, sendCommand, startDemoScenario, subscribeRun } from './state/api';
import type { BackendState, DemoStatus, GuardianEvent, HeroTiming, ModelStatus, OnboardingState, PresenceState, TimelineEvent } from './state/types';
import ActionPanel from './ui/ActionPanel';
import OnboardingFlow from './ui/OnboardingFlow';
import { pushEvent, store } from './state/store';
import { getOrFetchWarm, invalidateWarmValues, writeWarmValue } from './state/warmCache';
import { BACKEND_URL } from '../shared/constants';

declare global {
  interface Window {
    auraDesktop?: {
      openLogs: () => Promise<string>;
      getPresenceState: () => Promise<PresenceState>;
      updatePresenceState: (patch: Partial<PresenceState>) => Promise<PresenceState>;
      updateSettings: (patch: Partial<PresenceState>) => Promise<PresenceState>;
      getOnboardingState: () => Promise<OnboardingState>;
      updateOnboardingState: (patch: Partial<OnboardingState>) => Promise<OnboardingState>;
      completeOnboarding: () => Promise<OnboardingState>;
      getBackendState: () => Promise<BackendState>;
      showOverlay: () => Promise<PresenceState>;
      hideOverlay: () => Promise<PresenceState>;
      showDashboard: () => Promise<PresenceState>;
      onPresenceState: (callback: (state: PresenceState) => void) => () => void;
      onBackendState: (callback: (state: BackendState) => void) => () => void;
    }
  }
}

const QUICK_ACTIONS = [
  'Summarize this',
  'Explain this',
  'Draft a reply to this',
  'Rewrite this better',
  'Research this and answer',
];

const EMPTY_PRESENCE: PresenceState = {
  hotkey: '',
  overlayEnabled: true,
  hotkeyRegistered: false,
  hotkeyError: '',
  overlayVisible: false,
  activeRunId: '',
  pendingApprovalRunId: '',
  lastRunStatus: 'idle',
};


const EMPTY_BACKEND: BackendState = {
  lifecycle: 'idle',
  connection: 'Disconnected',
  url: BACKEND_URL,
  managedByDesktop: false,
  usingExternalBackend: false,
  launchAttempted: false,
  message: 'Desktop backend status is not available yet.',
  detail: '',
  healthCheckedAt: null,
  pid: null,
  backendDir: '',
  pythonCommand: '',
  startupCommand: [],
  startupLog: '',
};


const MODEL_STATUS_TTL_MS = 15000;
const HERO_CONTEXT_TTL_MS = 5000;
const GUARDIAN_TTL_MS = 3000;
const OVERLAY_AUTO_DISMISS_MS = 1400;

const AURA_STYLES = `
  :root {
    color-scheme: dark;
    --aura-bg: #07111f;
    --aura-bg-soft: #0d1728;
    --aura-panel: rgba(11, 20, 36, 0.88);
    --aura-panel-solid: #0f1b31;
    --aura-panel-light: #f8fbff;
    --aura-panel-light-border: #d9e5f6;
    --aura-border: rgba(148, 163, 184, 0.22);
    --aura-border-strong: rgba(96, 165, 250, 0.38);
    --aura-text: #e8eef8;
    --aura-text-soft: #a8b6cc;
    --aura-text-dark: #112033;
    --aura-primary: #7cc4ff;
    --aura-primary-strong: #4ea8ff;
    --aura-success: #6ee7b7;
    --aura-warning: #fbbf24;
    --aura-danger: #fca5a5;
    --aura-radius: 18px;
    --aura-radius-sm: 12px;
    --aura-shadow: 0 18px 60px rgba(2, 8, 23, 0.42);
    --aura-glow: 0 0 0 1px rgba(124, 196, 255, 0.12), 0 18px 44px rgba(59, 130, 246, 0.16);
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    background:
      radial-gradient(circle at top, rgba(56, 189, 248, 0.10), transparent 26%),
      radial-gradient(circle at right top, rgba(99, 102, 241, 0.12), transparent 22%),
      linear-gradient(180deg, #08111e 0%, #07111f 100%);
    color: var(--aura-text);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }

  .aura-root {
    min-height: 100vh;
    color: var(--aura-text);
  }

  .aura-shell {
    position: relative;
  }

  .aura-shell::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: radial-gradient(circle at top left, rgba(76, 201, 240, 0.08), transparent 28%);
  }

  .aura-button,
  .aura-root button {
    appearance: none;
    border: 1px solid rgba(148, 163, 184, 0.2);
    background: rgba(15, 23, 42, 0.92);
    color: var(--aura-text);
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 600;
    transition: transform 140ms ease, border-color 160ms ease, background 160ms ease, box-shadow 160ms ease, opacity 160ms ease;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
  }

  .aura-button:hover,
  .aura-root button:hover {
    transform: translateY(-1px);
    border-color: rgba(124, 196, 255, 0.34);
    box-shadow: 0 10px 24px rgba(8, 15, 28, 0.24);
  }

  .aura-button:disabled,
  .aura-root button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  .aura-button-primary {
    background: linear-gradient(135deg, rgba(88, 166, 255, 0.96), rgba(74, 222, 128, 0.82));
    color: #06101e;
    border-color: rgba(125, 211, 252, 0.55);
    box-shadow: 0 16px 28px rgba(56, 189, 248, 0.18);
  }

  .aura-button-danger {
    background: rgba(127, 29, 29, 0.8);
    border-color: rgba(252, 165, 165, 0.28);
  }

  .aura-button-ghost {
    background: rgba(15, 23, 42, 0.42);
  }

  .aura-root input,
  .aura-root textarea,
  .aura-root select {
    width: 100%;
    background: rgba(8, 15, 28, 0.72);
    color: var(--aura-text);
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 14px;
    padding: 12px 14px;
    font: inherit;
    transition: border-color 160ms ease, box-shadow 160ms ease, background 160ms ease;
  }

  .aura-root input:focus,
  .aura-root textarea:focus,
  .aura-root select:focus {
    outline: none;
    border-color: rgba(124, 196, 255, 0.55);
    box-shadow: 0 0 0 3px rgba(76, 201, 240, 0.10);
    background: rgba(11, 19, 34, 0.9);
  }

  .aura-card {
    border-radius: var(--aura-radius);
    border: 1px solid var(--aura-border);
    background: var(--aura-panel);
    backdrop-filter: blur(14px);
    box-shadow: var(--aura-shadow);
  }

  .aura-card-light {
    background: rgba(248, 251, 255, 0.96);
    border-color: var(--aura-panel-light-border);
    color: var(--aura-text-dark);
    box-shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
  }

  .aura-card-glow {
    box-shadow: var(--aura-glow);
  }

  .aura-section {
    padding: 18px;
    margin-bottom: 16px;
  }

  .aura-section-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
  }

  .aura-title {
    margin: 0;
    font-size: 14px;
    letter-spacing: 0.01em;
  }

  .aura-subtitle,
  .aura-meta {
    color: var(--aura-text-soft);
    font-size: 12px;
    line-height: 1.5;
  }

  .aura-kicker {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 4px 10px;
    border-radius: 999px;
    border: 1px solid rgba(124, 196, 255, 0.18);
    color: var(--aura-primary);
    background: rgba(59, 130, 246, 0.10);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .aura-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: 999px;
    padding: 6px 10px;
    border: 1px solid rgba(148, 163, 184, 0.2);
    background: rgba(15, 23, 42, 0.6);
    color: var(--aura-text);
    font-size: 12px;
    font-weight: 600;
  }

  .aura-badge-success { border-color: rgba(110, 231, 183, 0.28); color: var(--aura-success); }
  .aura-badge-warning { border-color: rgba(251, 191, 36, 0.28); color: var(--aura-warning); }
  .aura-badge-danger { border-color: rgba(252, 165, 165, 0.28); color: var(--aura-danger); }
  .aura-badge-accent { border-color: rgba(124, 196, 255, 0.32); color: var(--aura-primary); }

  .aura-chip-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .aura-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.16);
    background: rgba(15, 23, 42, 0.52);
    color: var(--aura-text);
    padding: 8px 12px;
    font-size: 12px;
  }

  .aura-grid-2 {
    display: grid;
    gap: 16px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .aura-grid-3 {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .aura-metric {
    padding: 12px;
    border-radius: 14px;
    background: rgba(15, 23, 42, 0.4);
    border: 1px solid rgba(148, 163, 184, 0.1);
  }

  .aura-metric-value {
    font-size: 18px;
    font-weight: 700;
    margin-top: 6px;
  }

  .aura-toolbar {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }

  .aura-stack-sm > * + * { margin-top: 8px; }
  .aura-stack-md > * + * { margin-top: 12px; }
  .aura-stack-lg > * + * { margin-top: 18px; }

  .aura-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(148,163,184,0.24), transparent);
    margin: 16px 0;
  }

  .aura-editor {
    min-height: 220px;
    line-height: 1.65;
    resize: vertical;
  }

  .aura-note {
    border-radius: 14px;
    padding: 12px 14px;
    border: 1px solid rgba(148, 163, 184, 0.16);
    background: rgba(15, 23, 42, 0.36);
  }

  .aura-note-warning {
    border-color: rgba(251, 191, 36, 0.22);
    background: rgba(120, 53, 15, 0.18);
  }

  .aura-note-danger {
    border-color: rgba(252, 165, 165, 0.24);
    background: rgba(127, 29, 29, 0.18);
  }

  .aura-hero-input {
    padding: 14px 16px !important;
    font-size: 15px;
  }

  .aura-surface-header {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: flex-start;
    margin-bottom: 18px;
  }

  .aura-page-title {
    margin: 0;
    font-size: 26px;
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  .aura-overlay-title {
    margin: 0;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  .aura-scroll-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: grid;
    gap: 10px;
  }

  .aura-light-text { color: var(--aura-text-dark); }

  .aura-detail-grid {
    display: grid;
    gap: 10px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .aura-code {
    white-space: pre-wrap;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
    line-height: 1.6;
    color: var(--aura-text-soft);
    margin: 0;
  }

  details.aura-disclosure {
    border-top: 1px solid rgba(148, 163, 184, 0.12);
    padding-top: 12px;
  }

  details.aura-disclosure summary {
    cursor: pointer;
    color: var(--aura-text-soft);
    font-size: 12px;
    font-weight: 600;
  }

  @media (max-width: 920px) {
    .aura-grid-2,
    .aura-grid-3,
    .aura-detail-grid {
      grid-template-columns: 1fr;
    }
  }
`;

const EMPTY_ONBOARDING: OnboardingState = {
  completed: false,
  currentStep: 'welcome',
  startedAt: null,
  completedAt: null,
  dismissedAt: null,
  starterPreferencesSeeded: false,
  firstTaskCompleted: false,
  firstTaskRunId: '',
  usageMode: 'assist',
  approvalMode: 'balanced',
  proactiveEnabled: true,
  lastKnownReadiness: {
    hotkeyReady: false,
    modelReady: false,
    permissionsChecked: false,
  },
};

type Surface = 'dashboard' | 'overlay';

function detectSurface(): Surface {
  return new URLSearchParams(window.location.search).get('surface') === 'overlay' ? 'overlay' : 'dashboard';
}

function AuraStyles() {
  return <style>{AURA_STYLES}</style>;
}

function toneForPhase(phase: string) {
  if (phase === 'completed') return 'success';
  if (phase === 'needs_attention') return 'danger';
  if (phase === 'awaiting_approval') return 'warning';
  return 'accent';
}

function looksLikeAssistCommand(text: string) {
  const lower = text.toLowerCase().trim();
  return ['summarize', 'reply', 'respond', 'rewrite', 'reword', 'explain', 'answer', 'research'].some((token) => lower.includes(token));
}

function readinessTone(ready: boolean, warning = false) {
  return ready ? 'success' : (warning ? 'warning' : 'danger');
}

function BackendStatusPanel({ backendState, modelStatus, compact = false }: { backendState: BackendState; modelStatus: ModelStatus | null; compact?: boolean }) {
  const backendHealthy = backendState.connection === 'Connected';
  const modelReady = Boolean(modelStatus?.assist_drafting_ready);
  const setupSteps = modelStatus?.setup_steps || [];
  const panelClass = compact ? 'aura-card aura-section' : 'aura-card aura-card-light aura-section';
  return <section className={panelClass}>
    <div className='aura-section-title'>
      <div>
        <h3 className={`aura-title ${compact ? '' : 'aura-light-text'}`}>Mac private-alpha readiness</h3>
        <div className={`aura-subtitle ${compact ? '' : 'aura-light-text'}`}>Bundled backend startup is automatic, but Python/Ollama requirements are still real.</div>
      </div>
      <div className='aura-chip-row'>
        <span className={`aura-badge aura-badge-${readinessTone(backendHealthy, backendState.lifecycle === 'starting')}`}>Backend {backendHealthy ? 'ready' : backendState.lifecycle}</span>
        <span className={`aura-badge aura-badge-${readinessTone(modelReady, !backendHealthy)}`}>Model {modelReady ? 'ready' : 'not ready'}</span>
      </div>
    </div>
    <div><strong>Backend:</strong> {backendState.message}</div>
    {!!backendState.detail && <div className='aura-note' style={{ marginTop: 10, whiteSpace: 'pre-wrap' }}>{backendState.detail}</div>}
    <div style={{ marginTop: 10 }}><strong>Drafting:</strong> {modelStatus?.summary || 'Checking local model readiness…'}</div>
    {!!modelStatus?.limitations?.length && <ul style={{ marginTop: 10 }}>
      {modelStatus.limitations.map((item) => <li key={item}>{item}</li>)}
    </ul>}
    {!modelReady && !!setupSteps.length && <div style={{ marginTop: 10 }}>
      <strong>Next steps</strong>
      <ol style={{ marginTop: 6 }}>
        {setupSteps.map((item) => <li key={item}>{item}</li>)}
      </ol>
    </div>}
    <div className='aura-meta' style={{ marginTop: 10 }}>
      Mac-first private alpha · unsigned app may require manual Open/Allow · real drafting requires local Ollama
    </div>
  </section>;
}

function useAuraRuntime(surface: Surface) {
  const [input, setInput] = useState('Summarize this');
  const [out, setOut] = useState('');
  const [runId, setRunId] = useState('');
  const [runStatus, setRunStatus] = useState('idle');
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [connection, setConnection] = useState<'Connected' | 'Disconnected'>('Disconnected');
  const [clarifications, setClarifications] = useState<any[]>([]);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [needsUser, setNeedsUser] = useState('');
  const [logsPath, setLogsPath] = useState('');
  const [currentUrl, setCurrentUrl] = useState('');
  const [sessionState, setSessionState] = useState('unknown');
  const [previewContext, setPreviewContext] = useState<any>(null);
  const [runState, setRunState] = useState<any>(null);
  const [draftText, setDraftText] = useState('');
  const [feedback, setFeedback] = useState('');
  const [presence, setPresence] = useState<PresenceState>(EMPTY_PRESENCE);
  const [onboarding, setOnboarding] = useState<OnboardingState>(EMPTY_ONBOARDING);
  const [onboardingVisible, setOnboardingVisible] = useState(false);
  const [personalization, setPersonalization] = useState<any>(null);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [backendState, setBackendState] = useState<BackendState>(EMPTY_BACKEND);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [demoStatus, setDemoStatus] = useState<DemoStatus>({ enabled: false, scenarios: [] });
  const [guardian, setGuardian] = useState<GuardianEvent[]>([]);

  const [prefs, setPrefs] = useState<any[]>([]);
  const [memories, setMemories] = useState<any[]>([]);
  const [sessions, setSessions] = useState<any[]>([]);
  const [storage, setStorage] = useState<any>({});
  const [safety, setSafety] = useState<any[]>([]);

  const streamRef = useRef<(() => void) | null>(null);
  const healthTimeoutRef = useRef<number | null>(null);
  const overlayDismissRef = useRef<number | null>(null);
  const runIdRef = useRef('');
  const surfaceTitle = surface === 'overlay' ? 'AURA Quick Invoke' : 'AURA Overlay';

  const syncPresence = async (patch: Partial<PresenceState>) => {
    if (!window.auraDesktop?.updatePresenceState) return;
    const hasChange = Object.entries(patch).some(([key, value]) => (presence as any)[key] !== value);
    if (!hasChange) return;
    const next = await window.auraDesktop.updatePresenceState(patch);
    setPresence(next);
  };

  const applyRunStateSync = (state: any, targetRunId: string) => {
    setRunState(state);
    runIdRef.current = targetRunId;
    setRunId(targetRunId);
    setDraftText(state?.approval_state?.edited_text || state?.approval_state?.draft_text || state?.draft_state?.draft_text || '');
    const approvalStatus = state?.approval_state?.status || state?.status || 'idle';
    const pending = approvalStatus === 'pending' || state?.status === 'awaiting_approval';
    setPersonalization(state?.draft_state?.personalization_profile || state?.plan?.assist?.personalization_profile || personalization);
    setRunStatus(state?.status || (pending ? 'awaiting_approval' : approvalStatus));
    setGuardian((state?.guardian_events || []).slice().reverse());
    if (pending) setNeedsUser('Draft ready for approval.');
    else if (state?.status === 'needs_user') setNeedsUser('Please complete the required manual action, then continue.');
    else if (approvalStatus === 'pasted' || approvalStatus === 'copied' || (state?.hero_timing?.phase === 'completed')) setNeedsUser('');
  };

  const refreshKnowledge = async () => {
    if (surface === 'overlay') return;
    const [p, m, ss, st, se, ge] = await Promise.all([
      fetch(`${BACKEND_URL}/preferences`).then(r => r.json()),
      fetch(`${BACKEND_URL}/memories`).then(r => r.json()),
      fetch(`${BACKEND_URL}/browser/sessions`).then(r => r.json()),
      fetch(`${BACKEND_URL}/storage/stats`).then(r => r.json()),
      fetch(`${BACKEND_URL}/safety/events`).then(r => r.json()),
      getOrFetchWarm('guardian:global', GUARDIAN_TTL_MS, () => getGuardianEvents(undefined, 12)),
    ]);
    setPrefs(p); setMemories(m); setSessions(ss); setStorage(st); setSafety(se); setGuardian(ge);
  };

  const refreshContext = async (force = false) => {
    try {
      const status = await getOrFetchWarm('model-status', MODEL_STATUS_TTL_MS, () => getModelStatus(), force);
      setModelStatus(status);
      const warmBundle = await getOrFetchWarm('hero-context', HERO_CONTEXT_TTL_MS, async () => {
        const proactive = await getProactiveSuggestions();
        const context = proactive?.captured_context || await captureAssistContext();
        const profile = proactive?.profile || await getAssistPersonalization('summarize', context);
        return { proactive, context, profile };
      }, force);
      setPreviewContext(warmBundle.context);
      setPersonalization(warmBundle.profile);
      setSuggestions(onboarding.proactiveEnabled === false ? [] : (warmBundle.proactive?.suggestions || []).slice(0, 3));
      if (!runIdRef.current) {
        const guardianKey = surface === 'overlay' ? 'guardian:overlay' : 'guardian:global';
        setGuardian(await getOrFetchWarm(guardianKey, GUARDIAN_TTL_MS, () => getGuardianEvents(undefined, 12), force));
      }
    } catch {
      // no-op for fast overlay refreshes
    }
  };

  const refreshModelStatus = async () => {
    try {
      setModelStatus(await getOrFetchWarm('model-status', MODEL_STATUS_TTL_MS, () => getModelStatus(), true));
    } catch {
      // no-op
    }
  };

  const refreshDemoStatus = async (force = false) => {
    try {
      setDemoStatus(await getOrFetchWarm('demo-status', MODEL_STATUS_TTL_MS, () => getDemoStatus(), force));
    } catch {
      // no-op
    }
  };

  const applyRunState = async (state: any, targetRunId: string) => {
    applyRunStateSync(state, targetRunId);
    writeWarmValue(`run-state:${targetRunId}`, state, GUARDIAN_TTL_MS);
    await syncPresence({
      activeRunId: targetRunId,
      pendingApprovalRunId: (state?.approval_state?.status === 'pending' || state?.status === 'awaiting_approval') ? targetRunId : '',
      lastRunStatus: state?.status || state?.approval_state?.status || 'idle',
    });
  };

  const refreshRunState = async (targetRunId = runId, force = false) => {
    if (!targetRunId) return;
    const state = await getOrFetchWarm(`run-state:${targetRunId}`, 600, () => getRunState(targetRunId), force);
    await applyRunState(state, targetRunId);
  };

  const attachRunStream = (targetRunId: string) => {
    streamRef.current?.();
    streamRef.current = subscribeRun(targetRunId, async (evt) => {
      pushEvent(evt);
      setEvents([...(store.eventsByRun[targetRunId] || [])]);
      if (evt.type === 'guardian_event') setGuardian(current => [evt as GuardianEvent, ...current].slice(0, 12));
      setRunStatus(evt.status || runStatus);
      if (evt.url) setCurrentUrl(evt.url);
      if (evt.session) setSessionState(evt.session);
      if (evt.type === 'needs_user') setNeedsUser(evt.message || 'User action required.');
      if (evt.type === 'approval_required') setNeedsUser('Draft ready for approval.');
      if (evt.type === 'resumed') setNeedsUser('');
      if (evt.type === 'step_status' && evt.name) {
        setRunState((current: any) => current ? {
          ...current,
          hero_timing: {
            ...(current.hero_timing || {}),
            phase: evt.name === 'Capture Context' ? 'capturing' : current.hero_timing?.phase,
          },
        } : current);
      }
      if (['needs_user', 'approval_required', 'run_cancelled'].includes(evt.type)) {
        invalidateWarmValues([`run-state:${targetRunId}`]);
        await refreshRunState(targetRunId, true);
      }
    });
  };

  useEffect(() => {
    let alive = true;
    let delay = 400;
    async function tick() {
      const ok = await healthcheck();
      if (!alive) return;
      setConnection(ok ? 'Connected' : 'Disconnected');
      delay = ok ? 1500 : Math.min(delay * 2, 5000);
      healthTimeoutRef.current = window.setTimeout(tick, delay);
    }
    tick();
    refreshKnowledge();
    refreshContext();
    refreshDemoStatus();

    window.auraDesktop?.getPresenceState?.().then(async (state) => {
      if (!alive) return;
      setPresence(state);
      const onboardingState = await window.auraDesktop?.getOnboardingState?.();
      if (onboardingState) {
        setOnboarding(onboardingState);
        setOnboardingVisible(!onboardingState.completed && surface === 'dashboard');
      }
      const pendingRunId = state.pendingApprovalRunId || state.activeRunId;
      if (pendingRunId) {
        attachRunStream(pendingRunId);
        await refreshRunState(pendingRunId);
      }
    }).catch(() => undefined);

    window.auraDesktop?.getBackendState?.().then((state) => {
      if (!alive || !state) return;
      setBackendState(state);
    }).catch(() => undefined);

    const unsubscribe = window.auraDesktop?.onPresenceState?.(async (state) => {
      if (!alive) return;
      setPresence(state);
      if (surface === 'overlay' && state.overlayVisible) await refreshContext(false);
      const targetRunId = state.pendingApprovalRunId || state.activeRunId;
      if (targetRunId && targetRunId !== runIdRef.current) {
        attachRunStream(targetRunId);
        await refreshRunState(targetRunId);
      }
    });
    const unsubscribeBackend = window.auraDesktop?.onBackendState?.((state) => {
      if (!alive) return;
      setBackendState(state);
    });

    const onFocus = () => { void refreshContext(false); };
    window.addEventListener('focus', onFocus);
    return () => {
      alive = false;
      unsubscribe?.();
      unsubscribeBackend?.();
      streamRef.current?.();
      if (healthTimeoutRef.current) window.clearTimeout(healthTimeoutRef.current);
      if (overlayDismissRef.current) window.clearTimeout(overlayDismissRef.current);
      window.removeEventListener('focus', onFocus);
    };
  }, []);

  useEffect(() => {
    if (backendState.connection === 'Connected') void refreshModelStatus();
  }, [backendState.connection]);

  useEffect(() => {
    if (!startedAt) return;
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 200);
    return () => clearInterval(t);
  }, [startedAt]);

  useEffect(() => {
    if (surface !== 'overlay') return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') void window.auraDesktop?.hideOverlay?.();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [surface]);

  useEffect(() => {
    if (surface !== 'overlay') return;
    const heroPhase = runState?.hero_timing?.phase;
    const pasteStatus = runState?.pasteback_state?.status;
    if (overlayDismissRef.current) window.clearTimeout(overlayDismissRef.current);
    if (heroPhase === 'completed' && pasteStatus === 'pasted') {
      overlayDismissRef.current = window.setTimeout(() => { void window.auraDesktop?.hideOverlay?.(); }, OVERLAY_AUTO_DISMISS_MS);
    }
  }, [surface, runState?.hero_timing?.phase, runState?.pasteback_state?.status]);

  const run = async (choices: Record<string, string> = {}, useMacro = false, proactiveSelection?: any, commandText?: string) => {
    const textToRun = commandText || input;
    invalidateWarmValues(['hero-context', 'guardian:overlay', 'guardian:global']);
    setRunState((current: any) => ({
      ...(current || {}),
      hero_timing: {
        ...(current?.hero_timing || {}),
        phase: 'capturing',
        phase_label: 'Capturing context',
        detail: 'Gathering the current app context for your request.',
      },
    }));
    const res = await sendCommand(textToRun, choices, useMacro, {
      suggestions_shown: suggestions,
      suggestion_selected: proactiveSelection?.action || null,
      suggestion_confidence: proactiveSelection?.confidence ?? null,
      signals_used: proactiveSelection?.signals_used || [],
      hero_timing: {
        overlay_invoked_at: presence.overlayInvokedAt || null,
        overlay_visible_at: presence.overlayVisibleAt || null,
        overlay_submitted_at: Date.now(),
      },
    });
    setOut(JSON.stringify(res, null, 2));
    setRunStatus(res.status || (res.ok ? 'running' : 'waiting'));
    if (res.run_id) {
      runIdRef.current = res.run_id;
      setRunId(res.run_id);
      setStartedAt(Date.now());
      attachRunStream(res.run_id);
      if (res.run_state) await applyRunState(res.run_state, res.run_id);
      else await refreshRunState(res.run_id, true);
    }
    setClarifications(res.clarifications || []);
    if (res.status === 'needs_user') setNeedsUser('Please complete the required manual action, then continue.');
    if (res.status === 'awaiting_approval') setNeedsUser('Draft ready for approval.');
  };

  const runDemo = async (scenarioId: string) => {
    invalidateWarmValues(['hero-context', 'guardian:overlay', 'guardian:global', 'demo-status']);
    setRunState((current: any) => ({
      ...(current || {}),
      hero_timing: {
        ...(current?.hero_timing || {}),
        phase: 'capturing',
        phase_label: 'Capturing context',
        detail: 'Loading a stable demo scenario.',
      },
    }));
    const res = await startDemoScenario(scenarioId, {
      overlay_invoked_at: presence.overlayInvokedAt || null,
      overlay_visible_at: presence.overlayVisibleAt || null,
      overlay_submitted_at: Date.now(),
    });
    setOut(JSON.stringify(res, null, 2));
    setRunStatus(res.status || (res.ok ? 'running' : 'waiting'));
    if (res.run_id) {
      runIdRef.current = res.run_id;
      setRunId(res.run_id);
      setStartedAt(Date.now());
      attachRunStream(res.run_id);
      if (res.run_state) await applyRunState(res.run_state, res.run_id);
      else await refreshRunState(res.run_id, true);
    }
    if (res.run_state?.captured_context) {
      setPreviewContext(res.run_state.captured_context);
    }
  };

  const approve = async () => {
    invalidateWarmValues([`run-state:${runId}`, 'guardian:overlay', 'guardian:global']);
    setRunState((current: any) => current ? { ...current, hero_timing: { ...(current.hero_timing || {}), phase: 'pasting', phase_label: 'Pasting', detail: 'Applying the approved draft back into the original target.' } } : current);
    const r = await approveRun(runId, draftText);
    setOut(JSON.stringify(r, null, 2));
    if (r.run_state) await applyRunState(r.run_state, runId);
    else await refreshRunState(runId, true);
  };

  const retry = async () => {
    invalidateWarmValues([`run-state:${runId}`]);
    setRunState((current: any) => current ? { ...current, hero_timing: { ...(current.hero_timing || {}), phase: 'drafting', phase_label: 'Drafting', detail: 'Updating the draft with your feedback.' } } : current);
    const r = await retryRun(runId, feedback);
    setOut(JSON.stringify(r, null, 2));
    if (r.run_state) await applyRunState(r.run_state, runId);
    else await refreshRunState(runId, true);
  };

  const reject = async () => {
    invalidateWarmValues([`run-state:${runId}`]);
    const r = await rejectRun(runId, feedback);
    setOut(JSON.stringify(r, null, 2));
    if (r.run_state) await applyRunState(r.run_state, runId);
    else await refreshRunState(runId, true);
  };

  const resume = async () => {
    invalidateWarmValues([`run-state:${runId}`]);
    const r = await resumeRun(runId);
    setOut(JSON.stringify(r, null, 2));
    if (r.run_state) await applyRunState(r.run_state, runId);
    else await refreshRunState(runId, true);
  };

  const updatePresenceSettings = async (patch: Partial<PresenceState>) => {
    if (!window.auraDesktop?.updateSettings) return;
    const next = await window.auraDesktop.updateSettings(patch);
    setPresence(next);
  };

  const updateOnboardingState = async (patch: Partial<OnboardingState>) => {
    if (!window.auraDesktop?.updateOnboardingState) return;
    const next = await window.auraDesktop.updateOnboardingState(patch);
    setOnboarding(next);
  };

  const completeOnboardingState = async () => {
    if (!window.auraDesktop?.completeOnboarding) return;
    const next = await window.auraDesktop.completeOnboarding();
    setOnboarding(next);
  };

  const autoChoices = Object.fromEntries(clarifications.map((c: any) => [c.key, c.options[0]]));
  const finalText = useMemo(() => runState?.approval_state?.final_text || draftText || events.filter((e) => e.status === 'success').map((e) => e.message).filter(Boolean).join('\n') || out, [events, out, runState, draftText]);
  const approvalState = runState?.approval_state || {};
  const capturedContext = runState?.captured_context || previewContext;
  const pendingApproval = approvalState.status === 'pending' || runStatus === 'awaiting_approval';
  const generation = runState?.assist?.generation || {};
  const captureMethod = capturedContext?.capture_method || {};
  const pasteState = runState?.pasteback_state || {};
  const demo = runState?.demo || {};
  const activeProfile = runState?.draft_state?.personalization_profile || personalization;
  const heroTiming = (runState?.hero_timing || {}) as HeroTiming;
  const heroPhase = (heroTiming.phase || (pendingApproval ? 'awaiting_approval' : (pasteState.status === 'pasted' ? 'completed' : (runStatus === 'running' ? 'capturing' : 'idle')))) as string;
  const heroLabel = heroTiming.phase_label || (heroPhase === 'awaiting_approval' ? 'Ready to review' : heroPhase === 'completed' ? 'Done' : heroPhase === 'pasting' ? 'Pasting' : heroPhase === 'drafting' ? 'Drafting' : heroPhase === 'capturing' ? 'Capturing context' : heroPhase === 'needs_attention' ? 'Needs attention' : 'Ready');
  const pasteIssue = pasteState.paste_blocked_reason || pasteState.context_drift_reason || pasteState.clipboard_restore_error_after_paste || null;
  const heroDetail = pasteIssue ? `Paste blocked: ${pasteIssue}` : (heroTiming.detail || (heroPhase === 'completed' ? 'AURA finished cleanly.' : heroPhase === 'awaiting_approval' ? 'Review the draft, then approve to paste it back.' : ''));
  const heroDurations = heroTiming.durations_ms || {};
  const recentGuardian = (runState?.guardian_events || guardian) as GuardianEvent[];
  const guardianWarnings = recentGuardian.filter((item: GuardianEvent) => item.risk !== 'low').slice(0, 3);
  const guardianBanner = guardianWarnings[0] || null;

    return {
    surface,
    surfaceTitle,
    input, setInput,
    out, runId, runStatus, elapsed, connection,
    clarifications, autoChoices, events, needsUser,
    logsPath, setLogsPath, currentUrl, sessionState,
    previewContext, runState, draftText, setDraftText, feedback, setFeedback,
    onboarding, setOnboarding, onboardingVisible, setOnboardingVisible, modelStatus, refreshModelStatus,
    backendState,
    personalization: activeProfile, suggestions, setSuggestions,
    prefs, memories, sessions, storage, safety, guardian: recentGuardian, guardianWarnings, guardianBanner,
    finalText, approvalState, capturedContext, pendingApproval, generation, captureMethod, pasteState,
    demoStatus, demo,
    heroTiming, heroPhase, heroLabel, heroDetail, heroDurations,
    presence,
    refreshKnowledge, refreshContext, refreshRunState,
    run, runDemo, approve, retry, reject, resume,
    updatePresenceSettings, updateOnboardingState, completeOnboardingState,
  };
}

function PersonalizationSummary({ profile }: { profile: any }) {
  const style = profile?.style_profile || {};
  const approval = profile?.approval_profile || {};
  const entries = [
    ['Length', style?.length_preference?.value, style?.length_preference?.confidence],
    ['Tone', style?.tone_preference?.value, style?.tone_preference?.confidence],
    ['Warmth', style?.warmth_preference?.value, style?.warmth_preference?.confidence],
    ['Structure', style?.structure_preference?.value, style?.structure_preference?.confidence],
    ['Research', style?.research_tendency?.value, style?.research_tendency?.confidence],
  ].filter(([, value]) => value);
  return <section className='aura-card aura-section aura-card-glow'>
    <div className='aura-section-title'>
      <div>
        <h3 className='aura-title'>Personalization</h3>
        <div className='aura-subtitle'>Style signals AURA is using right now.</div>
      </div>
      <span className={`aura-badge aura-badge-${approval?.recommended_caution === 'strict' ? 'danger' : approval?.recommended_caution === 'elevated' ? 'warning' : 'accent'}`}>
        {approval?.recommended_caution || 'normal'} caution
      </span>
    </div>
    <div className='aura-chip-row'>
      {entries.map(([label, value, confidence]) => <span key={String(label)} className='aura-chip'>{label}: {String(value)} · {Math.round(Number(confidence || 0) * 100)}%</span>)}
      <span className='aura-chip'>Edit frequency: {approval?.edit_frequency ?? 0}</span>
    </div>
  </section>;
}

function SuggestionChips({ suggestions, onSelect }: { suggestions: any[]; onSelect: (command: string) => void }) {
  if (!suggestions?.length) return null;
  return <div className='aura-stack-sm'>
    <div className='aura-section-title' style={{ marginBottom: 8 }}>
      <div>
        <h3 className='aura-title'>Suggested next actions</h3>
        <div className='aura-subtitle'>Quick, context-aware prompts.</div>
      </div>
    </div>
    <div className='aura-chip-row'>
      {suggestions.map((item) => <button key={item.command} className='aura-button aura-button-ghost' title={item.reason} onClick={() => onSelect(item.command)}>{item.label}</button>)}
    </div>
  </div>;
}

function formatDuration(value?: number | null) {
  if (value === null || value === undefined) return '-';
  if (value < 1000) return `${value}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

function HeroFlowBanner({ label, detail, phase, durations, compact = false }: { label: string; detail: string; phase: string; durations: Record<string, number | null>; compact?: boolean }) {
  const palette = phase === 'completed' ? { bg: compact ? '#14532d' : '#ecfdf5', border: '#86efac' } : phase === 'needs_attention' ? { bg: compact ? '#7f1d1d' : '#fef2f2', border: '#fca5a5' } : { bg: compact ? '#1e293b' : '#eff6ff', border: '#93c5fd' };
  const chips = [
    ['Capture', durations.overlay_submit_to_context_capture_complete],
    ['Model', durations.model_request_duration],
    ['Approval', durations.approval_wait_duration],
    ['Paste', durations.pasteback_duration],
    ['Total', durations.total_run_duration],
  ].filter(([, value]) => value !== null && value !== undefined);
  return <section data-testid='hero-flow-banner' className={`aura-section ${compact ? 'aura-card' : 'aura-card aura-card-light'} aura-card-glow`} style={{ background: palette.bg, color: compact ? '#f8fafc' : 'inherit', border: `1px solid ${palette.border}` }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
      <div>
        <div className={`aura-badge aura-badge-${toneForPhase(phase)}`} style={{ marginBottom: 10 }}>{phase.replace('_', ' ')}</div>
        <strong>{label}</strong>
        <div style={{ marginTop: 4, opacity: 0.9 }}>{detail}</div>
      </div>
      {!!chips.length && <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {chips.map(([name, value]) => <span key={String(name)} className='aura-chip' style={{ border: `1px solid ${palette.border}`, color: compact ? '#f8fafc' : 'inherit' }}>{name}: {formatDuration(Number(value))}</span>)}
      </div>}
    </div>
  </section>;
}

function HeroTimingPanel({ heroTiming }: { heroTiming: HeroTiming }) {
  const marks = heroTiming?.marks || {};
  const durations = heroTiming?.durations_ms || {};
  if (!Object.keys(marks).length && !Object.keys(durations).length) return null;
  return <section className='aura-card aura-card-light aura-section'>
    <div className='aura-section-title'>
      <div>
        <h3 className='aura-title aura-light-text'>Hero flow timings</h3>
        <div className='aura-subtitle aura-light-text'>Diagnostic detail without dominating the product surface.</div>
      </div>
    </div>
    <div className='aura-chip-row'>
      {Object.entries(durations).map(([key, value]) => <span key={key} className='aura-chip' style={{ color: '#112033', background: 'rgba(17,32,51,0.06)' }}>{key}: {formatDuration(value as number | null)}</span>)}
    </div>
    <details className='aura-disclosure' style={{ marginTop: 12 }}>
      <summary>Raw timing marks</summary>
      <pre className='aura-code' style={{ color: '#334155' }}>{JSON.stringify(marks, null, 2)}</pre>
    </details>
  </section>;
}

function DemoPanel({ demoStatus, activeDemo, onRun, compact = false }: { demoStatus: DemoStatus; activeDemo: any; onRun: (scenarioId: string) => void; compact?: boolean }) {
  if (!demoStatus?.enabled) return null;
  return <section className={`aura-section ${compact ? 'aura-card' : 'aura-card aura-card-light'}`}>
    <div className='aura-section-title'>
      <div>
        <div className='aura-kicker'>Demo mode</div>
        <div style={{ marginTop: 10, fontWeight: 700 }}>Stable scenarios for a fast 15–20 second demo.</div>
      </div>
      {activeDemo?.scenario_label && <span className='aura-badge aura-badge-accent'>
        Active: {activeDemo.scenario_label}
      </span>}
    </div>
    <div className='aura-chip-row'>
      {(demoStatus.scenarios || []).map((scenario) => <button key={scenario.id} className='aura-button aura-button-ghost' onClick={() => onRun(scenario.id)}>
        Try Demo: {scenario.label}
      </button>)}
    </div>
    {!!activeDemo?.fallbacks?.length && <div className='aura-meta' style={{ marginTop: 10 }}>
      Demo fallbacks used: {activeDemo.fallbacks.join(', ')}
    </div>}
  </section>;
}

function GuardianPanel({ events, title = 'Guardian activity', compact = false }: { events: GuardianEvent[]; title?: string; compact?: boolean }) {
  if (!events?.length) return null;
  return <section className={`aura-section ${compact ? 'aura-card' : 'aura-card aura-card-light'}`}>
    <div className='aura-section-title'>
      <div>
        <h3 className={`aura-title ${compact ? '' : 'aura-light-text'}`}>{title}</h3>
        <div className={`aura-subtitle ${compact ? '' : 'aura-light-text'}`}>Guardian keeps the product trustworthy without turning noisy.</div>
      </div>
    </div>
    <ul className='aura-scroll-list'>
      {events.map((event, index) => <li key={`${event.timestamp || index}-${event.summary}`} className='aura-note'>
        <div className='aura-section-title' style={{ marginBottom: 6 }}>
          <span className={`aura-badge aura-badge-${event.risk === 'high' ? 'danger' : event.risk === 'medium' ? 'warning' : 'accent'}`}>{event.risk}</span>
          <span className='aura-meta'>{event.source}</span>
        </div>
        <div style={{ fontWeight: 600 }}>{event.summary}</div>
        <div className='aura-meta' style={{ marginTop: 6 }}>{event.explanation}</div>
      </li>)}
    </ul>
  </section>;
}

function GuardianBanner({ event, compact = false }: { event: GuardianEvent | null; compact?: boolean }) {
  if (!event) return null;
  return <div role='alert' className={`aura-note ${event.risk === 'high' ? 'aura-note-danger' : 'aura-note-warning'}`} style={{ marginBottom: 12 }}>
    <div className='aura-section-title' style={{ marginBottom: 6 }}>
      <span className={`aura-badge aura-badge-${event.risk === 'high' ? 'danger' : 'warning'}`}>{event.risk === 'high' ? 'Guardian warning' : 'Guardian note'}</span>
      <span className='aura-meta'>{compact ? 'Overlay trust check' : 'Guardian'}</span>
    </div>
    <div style={{ fontWeight: 600 }}>{event.summary}</div>
    <div className='aura-meta' style={{ marginTop: 6 }}>{event.explanation}</div>
  </div>;
}

function PresenceStatus({ presence, onToggleOverlay, onHotkeyChange, onShowOverlay }: { presence: PresenceState; onToggleOverlay: (enabled: boolean) => void; onHotkeyChange: (hotkey: string) => void; onShowOverlay: () => void; }) {
  const [draftHotkey, setDraftHotkey] = useState(presence.hotkey || '');
  useEffect(() => setDraftHotkey(presence.hotkey || ''), [presence.hotkey]);
  return <section className='aura-card aura-card-light aura-section'>
    <div className='aura-section-title'>
      <div>
        <h3 className='aura-title aura-light-text'>Presence</h3>
        <div className='aura-subtitle aura-light-text'>Global invoke controls and overlay availability.</div>
      </div>
      <span className={`aura-badge aura-badge-${presence.hotkeyRegistered ? 'success' : 'warning'}`}>
        {presence.hotkeyRegistered ? 'hotkey ready' : 'hotkey unavailable'}
      </span>
    </div>
    <div className='aura-grid-3'>
      <div className='aura-metric'><div className='aura-meta aura-light-text'>Hotkey</div><div className='aura-metric-value aura-light-text'>{presence.hotkey || '-'}</div></div>
      <div className='aura-metric'><div className='aura-meta aura-light-text'>Overlay</div><div className='aura-metric-value aura-light-text'>{presence.overlayEnabled ? 'Enabled' : 'Disabled'}</div></div>
      <div className='aura-metric'><div className='aura-meta aura-light-text'>Pending review</div><div className='aura-metric-value aura-light-text'>{presence.pendingApprovalRunId || '-'}</div></div>
    </div>
    {presence.hotkeyError && <div role='alert' className='aura-note aura-note-warning' style={{ marginTop: 12 }}><strong>Hotkey error:</strong> {presence.hotkeyError}</div>}
    <div className='aura-toolbar' style={{ marginTop: 12 }}>
      <input aria-label='presence hotkey' value={draftHotkey} onChange={e => setDraftHotkey(e.target.value)} style={{ width: 220, maxWidth: 220 }} />
      <button className='aura-button aura-button-primary' onClick={() => onHotkeyChange(draftHotkey)}>Save Hotkey</button>
      <button className='aura-button aura-button-ghost' onClick={() => onToggleOverlay(!presence.overlayEnabled)}>{presence.overlayEnabled ? 'Disable Overlay' : 'Enable Overlay'}</button>
      <button className='aura-button aura-button-ghost' onClick={onShowOverlay}>Open Quick Overlay</button>
    </div>
  </section>;
}

function OverlaySurface(runtime: ReturnType<typeof useAuraRuntime>) {
  return <div className='aura-root aura-shell' style={{ padding: 16 }}>
    <div className='aura-surface-header'>
      <div>
        <div className='aura-kicker'>Quick invoke</div>
        <h1 className='aura-overlay-title' style={{ marginTop: 12 }}>{runtime.surfaceTitle}</h1>
        <div className='aura-subtitle'>Fast assist, polished review, and reliable demoable flow.</div>
      </div>
      <div className='aura-chip-row'>
        <span className={`aura-badge aura-badge-${runtime.connection === 'Connected' ? 'success' : 'warning'}`}>{runtime.connection}</span>
        <span className='aura-badge aura-badge-accent'>Hotkey {runtime.presence.hotkey || '-'}</span>
        <button className='aura-button aura-button-ghost' onClick={() => window.auraDesktop?.showDashboard?.()}>Open Full App</button>
        <button className='aura-button aura-button-ghost' onClick={() => window.auraDesktop?.hideOverlay?.()}>Dismiss</button>
      </div>
    </div>

    {!runtime.presence.hotkeyRegistered && runtime.presence.hotkeyError && <div role='alert' className='aura-note aura-note-danger'>
      <strong>Hotkey unavailable:</strong> {runtime.presence.hotkeyError}
    </div>}

    <BackendStatusPanel backendState={runtime.backendState} modelStatus={runtime.modelStatus} compact />

    <section className='aura-card aura-section'>
      <div className='aura-section-title'>
        <div>
          <h3 className='aura-title'>Current context</h3>
          <div className='aura-subtitle'>A compact, trustworthy snapshot of what AURA is working with.</div>
        </div>
        <span className='aura-badge aura-badge-accent'>{runtime.capturedContext?.capture_path_used || runtime.capturedContext?.input_source || 'waiting'}</span>
      </div>
      <div><strong>App:</strong> {runtime.capturedContext?.active_app || '-'}</div>
      <div><strong>Window:</strong> {runtime.capturedContext?.window_title || '-'}</div>
      <div><strong>Selected/clipboard available:</strong> {runtime.capturedContext?.input_text ? 'likely yes' : 'not detected yet'}</div>
    </section>

    <DemoPanel demoStatus={runtime.demoStatus} activeDemo={runtime.demo} onRun={runtime.runDemo} compact />

    <section className='aura-card aura-section aura-card-glow'>
      <SuggestionChips suggestions={runtime.suggestions} onSelect={(command) => {
        const suggestion = runtime.suggestions.find((item: any) => item.command === command);
        runtime.setInput(command);
        if (suggestion) void runtime.run({}, false, suggestion, command);
      }} />
      <div className='aura-divider' />
      <input className='aura-hero-input' value={runtime.input} onChange={e => runtime.setInput(e.target.value)} placeholder='Ask AURA to summarize, reply, rewrite, or explain…' />
      <div className='aura-toolbar' style={{ marginTop: 12 }}>
        <button className='aura-button aura-button-primary' onClick={() => runtime.run()}>Run</button>
        <button className='aura-button aura-button-ghost' onClick={() => runtime.refreshContext()}>Refresh context</button>
        <button className='aura-button aura-button-ghost' onClick={() => runtime.run(runtime.autoChoices)} disabled={!runtime.clarifications.length}>Answer Clarifications</button>
      </div>
    </section>
    <PersonalizationSummary profile={runtime.personalization} />

    <HeroFlowBanner label={runtime.heroLabel} detail={runtime.heroDetail} phase={runtime.heroPhase} durations={runtime.heroDurations} compact />
    <GuardianBanner event={runtime.guardianBanner} compact />

    <section className='aura-card aura-section'>
      <div className='aura-grid-3'>
        <div className='aura-metric'><div className='aura-meta'>Run</div><div className='aura-metric-value'>{runtime.runId || '-'}</div></div>
        <div className='aura-metric'><div className='aura-meta'>Approval</div><div className='aura-metric-value'>{runtime.approvalState.status || 'not requested'}</div></div>
        <div className='aura-metric'><div className='aura-meta'>Revalidation</div><div className='aura-metric-value'>{runtime.pasteState.target_validation_result || runtime.pasteState.target_validation || '-'}</div></div>
      </div>
      {(runtime.needsUser || runtime.demo?.fallbacks?.length || runtime.demo?.scenario_label) && <div className='aura-note aura-note-warning' style={{ marginTop: 12 }}>
        <div><strong>Demo:</strong> {runtime.demo?.scenario_label || '-'}</div>
        <div><strong>Fallbacks:</strong> {(runtime.demo?.fallbacks || []).join(', ') || '-'}</div>
        <div><strong>Paste issue:</strong> {runtime.pasteState.paste_blocked_reason || runtime.pasteState.context_drift_reason || runtime.pasteState.clipboard_restore_error_after_paste || '-'}</div>
        {runtime.needsUser && <div style={{ marginTop: 6 }}>{runtime.needsUser}</div>}
      </div>}
    </section>

    <GuardianPanel events={runtime.guardianWarnings} title='Guardian warnings' compact />

    <section className='aura-card aura-section aura-card-glow'>
      <div className='aura-section-title'>
        <div>
          <h3 className='aura-title'>Draft review</h3>
          <div className='aura-subtitle'>Readable, low-friction approval space with clear action hierarchy.</div>
        </div>
        <span className={`aura-badge aura-badge-${runtime.pendingApproval ? 'warning' : 'success'}`}>{runtime.pendingApproval ? 'review required' : 'up to date'}</span>
      </div>
      <div className='aura-chip-row' style={{ marginBottom: 12 }}>
        {runtime.runState?.draft_state?.style_hints ? Object.entries(runtime.runState.draft_state.style_hints).map(([key, value]) => <span key={key} className='aura-chip'>{key}: {String(value)}</span>) : <span className='aura-chip'>Applied style: not available yet</span>}
      </div>
      <textarea className='aura-editor' aria-label='draft editor' value={runtime.draftText} onChange={e => runtime.setDraftText(e.target.value)} rows={10} placeholder='Generated draft will appear here.' />
      <input aria-label='retry feedback' value={runtime.feedback} onChange={e => runtime.setFeedback(e.target.value)} placeholder='Optional retry feedback' style={{ marginTop: 12 }} />
      <div className='aura-toolbar' style={{ marginTop: 12 }}>
        <button className='aura-button aura-button-primary' disabled={!runtime.runId || !runtime.pendingApproval} onClick={runtime.approve}>Approve & Paste</button>
        <button className='aura-button aura-button-ghost' disabled={!runtime.runId || !runtime.pendingApproval} onClick={runtime.retry}>Retry</button>
        <button className='aura-button aura-button-danger' disabled={!runtime.runId || !runtime.pendingApproval} onClick={runtime.reject}>Reject</button>
        <button className='aura-button aura-button-ghost' disabled={!runtime.runId || runtime.pendingApproval} onClick={runtime.resume}>Continue</button>
      </div>
    </section>
  </div>;
}

function DashboardSurface(runtime: ReturnType<typeof useAuraRuntime>) {
  if (runtime.onboardingVisible) {
    return <div style={{ fontFamily: 'Inter, sans-serif', maxWidth: 980, margin: '0 auto', padding: 16 }}>
      <h1>{runtime.surfaceTitle}</h1>
      <p><strong>Backend:</strong> {runtime.connection}</p>
      <OnboardingFlow
        onboardingState={runtime.onboarding}
        presence={runtime.presence}
        backendState={runtime.backendState}
        modelStatus={runtime.modelStatus}
        capturedContext={runtime.capturedContext}
        runId={runtime.runId}
        runStatus={runtime.runStatus}
        pendingApproval={runtime.pendingApproval}
        draftText={runtime.draftText}
        setDraftText={runtime.setDraftText}
        finalText={runtime.finalText}
        approvalState={runtime.approvalState}
        pasteState={runtime.pasteState}
        setInput={runtime.setInput}
        refreshContext={runtime.refreshContext}
        run={runtime.run}
        approve={runtime.approve}
        updatePresenceSettings={runtime.updatePresenceSettings}
        updateOnboardingState={runtime.updateOnboardingState}
        completeOnboarding={runtime.completeOnboardingState}
        closeOnboarding={async () => {
          setTimeout(() => runtime.setOnboardingVisible(false), 0);
          await runtime.updateOnboardingState({ dismissedAt: new Date().toISOString() });
        }}
      />
    </div>;
  }

  return <div className='aura-root aura-shell' style={{ maxWidth: 1120, margin: '0 auto', padding: 20 }}>
    <div className='aura-surface-header'>
      <div>
        <div className='aura-kicker'>AURA desktop</div>
        <h1 className='aura-page-title' style={{ marginTop: 12 }}>{runtime.surfaceTitle}</h1>
        <div className='aura-subtitle'>A premium command center for assist, review, and trusted automation.</div>
      </div>
      <div className='aura-chip-row'>
        <span className={`aura-badge aura-badge-${runtime.connection === 'Connected' ? 'success' : 'warning'}`}>Backend {runtime.connection}</span>
        <span className='aura-badge aura-badge-accent'>{runtime.runStatus}</span>
      </div>
    </div>
    {!runtime.onboardingVisible && !runtime.onboarding.completed && <section style={{ border: '1px solid #e2e8f0', borderRadius: 12, padding: 12, marginBottom: 12, background: '#fff' }}>
      <strong>Onboarding is still in progress.</strong>
      <div style={{ marginTop: 8 }}>
        <button onClick={() => runtime.setOnboardingVisible(true)}>Resume onboarding</button>
      </div>
    </section>}
    {runtime.onboarding.completed && !runtime.onboardingVisible && <section style={{ border: '1px solid #e2e8f0', borderRadius: 12, padding: 12, marginBottom: 12, background: '#fff' }}>
      <strong>AURA is ready.</strong>
      <div style={{ marginTop: 8 }}>
        <button onClick={() => runtime.setOnboardingVisible(true)}>Reopen onboarding</button>
      </div>
    </section>}
    <PresenceStatus
      presence={runtime.presence}
      onToggleOverlay={(enabled) => runtime.updatePresenceSettings({ overlayEnabled: enabled })}
      onHotkeyChange={(hotkey) => runtime.updatePresenceSettings({ hotkey })}
      onShowOverlay={() => window.auraDesktop?.showOverlay?.()}
    />
    <BackendStatusPanel backendState={runtime.backendState} modelStatus={runtime.modelStatus} />
    <DemoPanel demoStatus={runtime.demoStatus} activeDemo={runtime.demo} onRun={runtime.runDemo} />
    <section className='aura-card aura-card-light aura-section'>
      <div className='aura-grid-3'>
        <div className='aura-metric'><div className='aura-meta aura-light-text'>Run</div><div className='aura-metric-value aura-light-text'>{runtime.runId || '-'}</div></div>
        <div className='aura-metric'><div className='aura-meta aura-light-text'>Elapsed</div><div className='aura-metric-value aura-light-text'>{runtime.elapsed}s</div></div>
        <div className='aura-metric'><div className='aura-meta aura-light-text'>Session</div><div className='aura-metric-value aura-light-text'>{runtime.sessionState}</div></div>
      </div>
      <div className='aura-meta aura-light-text' style={{ marginTop: 12 }}>Current URL: {runtime.currentUrl || runtime.capturedContext?.browser_url || '-'}</div>
    </section>

    <HeroFlowBanner label={runtime.heroLabel} detail={runtime.heroDetail} phase={runtime.heroPhase} durations={runtime.heroDurations} />
    <GuardianBanner event={runtime.guardianBanner} />

    {runtime.needsUser && <div role='alert' className='aura-note aura-note-warning' style={{ marginBottom: 10 }}>
      <strong>{runtime.pendingApproval ? 'Approval needed:' : 'Action needed:'}</strong> {runtime.needsUser}
      {!runtime.pendingApproval && <div style={{ marginTop: 8 }}><button onClick={runtime.resume}>Continue</button></div>}
    </div>}

    <section className='aura-card aura-section aura-card-glow'>
      <SuggestionChips suggestions={runtime.suggestions} onSelect={(command) => {
        const suggestion = runtime.suggestions.find((item: any) => item.command === command);
        runtime.setInput(command);
        if (suggestion) void runtime.run({}, false, suggestion, command);
      }} />
      <div className='aura-divider' />
      <div className='aura-toolbar' style={{ marginBottom: 12 }}>
        {QUICK_ACTIONS.map(action => <button key={action} className='aura-button aura-button-ghost' onClick={() => runtime.setInput(action)}>{action}</button>)}
        <button className='aura-button aura-button-ghost' onClick={() => runtime.refreshContext()}>Refresh capture</button>
      </div>
      <input className='aura-hero-input' value={runtime.input} onChange={e => runtime.setInput(e.target.value)} placeholder='Type command' />
      <div className='aura-toolbar' style={{ marginTop: 12 }}>
        <button className='aura-button aura-button-primary' onClick={() => runtime.run()}>Run</button>
        <button className='aura-button aura-button-danger' onClick={() => panicStop(runtime.runId)} disabled={!runtime.runId}>Panic Stop</button>
        {!!runtime.clarifications.length && <button className='aura-button aura-button-ghost' onClick={() => runtime.run(runtime.autoChoices)}>Answer Clarifications</button>}
        <button className='aura-button aura-button-ghost' onClick={() => navigator.clipboard.writeText(runtime.finalText)}>Copy final answer</button>
        <button className='aura-button aura-button-ghost' onClick={async () => {
      if (window.auraDesktop?.openLogs) runtime.setLogsPath(await window.auraDesktop.openLogs());
      else runtime.setLogsPath('No desktop bridge. Logs: system default location.');
    }}>Open logs folder</button>
        <button className='aura-button aura-button-ghost' onClick={runtime.refreshKnowledge}>Refresh Panels</button>
      </div>
    </section>
    {runtime.logsPath && <p>Logs: {runtime.logsPath}</p>}

    <div className='aura-grid-2' style={{ marginTop: 12, marginBottom: 12 }}>
      <section className='aura-card aura-card-light aura-section'>
        <div className='aura-section-title'>
          <div>
            <h3 className='aura-title aura-light-text'>Captured context</h3>
            <div className='aura-subtitle aura-light-text'>Clear source visibility without raw-debug overload.</div>
          </div>
        </div>
        <div><strong>App:</strong> {runtime.capturedContext?.active_app || '-'}</div>
        <div><strong>Window:</strong> {runtime.capturedContext?.window_title || '-'}</div>
        <div><strong>Capture Path:</strong> {runtime.capturedContext?.capture_path_used || runtime.capturedContext?.input_source || '-'}</div>
        <div><strong>Clipboard preserved:</strong> {runtime.captureMethod.clipboard_preserved === undefined ? '-' : String(runtime.captureMethod.clipboard_preserved)}</div>
        <div><strong>Clipboard restored:</strong> {runtime.captureMethod.clipboard_restored_after_capture === undefined ? '-' : String(runtime.captureMethod.clipboard_restored_after_capture)}</div>
        <div><strong>Browser URL:</strong> {runtime.capturedContext?.browser_url || '-'}</div>
        <div className='aura-note' style={{ marginTop: 12 }}><pre className='aura-code' style={{ color: '#334155' }}>{runtime.capturedContext?.input_text || 'Select or copy text in another app, then run an assist command.'}</pre></div>
      </section>

      <section className='aura-card aura-card-light aura-section aura-card-glow'>
        <div className='aura-section-title'>
          <div>
            <h3 className='aura-title aura-light-text'>Draft review</h3>
            <div className='aura-subtitle aura-light-text'>Readable formatting, clear actions, subtle style cues.</div>
          </div>
          <span className={`aura-badge aura-badge-${runtime.pendingApproval ? 'warning' : 'success'}`}>{runtime.pendingApproval ? 'approval needed' : 'synced'}</span>
        </div>
        <div><strong>Approval:</strong> {runtime.approvalState.status || 'not requested'}</div>
        <div><strong>Demo scenario:</strong> {runtime.demo?.scenario_label || '-'}</div>
        <div><strong>Generation:</strong> {runtime.generation.provider ? `${runtime.generation.provider}${runtime.generation.model ? ` / ${runtime.generation.model}` : ''}` : '-'}</div>
        <div><strong>Confidence:</strong> {runtime.generation.confidence ?? '-'}</div>
        <div className='aura-chip-row' style={{ marginTop: 12, marginBottom: 12 }}>
          {runtime.runState?.draft_state?.style_hints ? Object.entries(runtime.runState.draft_state.style_hints).map(([key, value]) => <span key={key} className='aura-chip' style={{ color: '#112033', background: 'rgba(17,32,51,0.06)' }}>{key}: {String(value)}</span>) : <span className='aura-chip' style={{ color: '#112033', background: 'rgba(17,32,51,0.06)' }}>Applied style signals: -</span>}
        </div>
        <div><strong>Revalidation:</strong> {runtime.pasteState.target_validation_result || runtime.pasteState.target_validation || '-'}</div>
        <div><strong>Paste issue:</strong> {runtime.pasteState.paste_blocked_reason || runtime.pasteState.context_drift_reason || runtime.pasteState.clipboard_restore_error_after_paste || '-'}</div>
        <div><strong>Fallbacks:</strong> {(runtime.demo?.fallbacks || []).join(', ') || '-'}</div>
        <textarea className='aura-editor' aria-label='draft editor' value={runtime.draftText} onChange={e => runtime.setDraftText(e.target.value)} rows={10} placeholder='Generated draft will appear here.' />
        <input aria-label='retry feedback' value={runtime.feedback} onChange={e => runtime.setFeedback(e.target.value)} placeholder='Optional retry feedback (e.g. make it more direct)' style={{ marginTop: 12 }} />
        <div className='aura-toolbar' style={{ marginTop: 12 }}>
          <button className='aura-button aura-button-primary' disabled={!runtime.runId || !runtime.pendingApproval} onClick={runtime.approve}>Approve & Paste</button>
          <button className='aura-button aura-button-ghost' disabled={!runtime.runId || !runtime.pendingApproval} onClick={runtime.retry}>Retry</button>
          <button className='aura-button aura-button-danger' disabled={!runtime.runId || !runtime.pendingApproval} onClick={runtime.reject}>Reject</button>
        </div>
      </section>
    </div>

    <PersonalizationSummary profile={runtime.personalization} />

    <HeroTimingPanel heroTiming={runtime.heroTiming} />

    <GuardianPanel events={runtime.guardian} />

    <ActionPanel events={runtime.events} />

    <section className='aura-card aura-card-light aura-section'>
      <div className='aura-section-title'>
        <div>
          <h3 className='aura-title aura-light-text'>System insights</h3>
          <div className='aura-subtitle aura-light-text'>Readable product intelligence instead of raw dev output.</div>
        </div>
      </div>
      <div className='aura-grid-2'>
        <div>
          <h4 className='aura-light-text'>Preferences</h4>
          <ul>{runtime.prefs.map((p: any) => <li key={p.decision_key}>{p.decision_key}: {p.value} ({Math.round((p.confidence || 0) * 100)}%)</li>)}</ul>
        </div>
        <div>
          <h4 className='aura-light-text'>Recent memories</h4>
          <ul>{runtime.memories.slice(0, 12).map((m: any) => <li key={m.id}>{m.key}: {m.value}</li>)}</ul>
        </div>
      </div>
      <details className='aura-disclosure' style={{ marginTop: 12 }}>
        <summary>More operational detail</summary>
        <div className='aura-grid-2' style={{ marginTop: 12 }}>
          <div><h4 className='aura-light-text'>Sessions</h4><ul>{runtime.sessions.map((s: any) => <li key={s.domain}>{s.domain}</li>)}</ul></div>
          <div><h4 className='aura-light-text'>Storage stats</h4><pre className='aura-code' style={{ color: '#334155' }}>{JSON.stringify(runtime.storage, null, 2)}</pre></div>
        </div>
        <div style={{ marginTop: 12 }}>
          <h4 className='aura-light-text'>Safety cockpit</h4>
          <ul>{runtime.safety.slice(-10).map((s, i) => <li key={i}>{s.kind} / {s.action || s.step_id} / {s.ok === false ? 'fail' : 'ok'}</li>)}</ul>
        </div>
        <div style={{ marginTop: 12 }}>
          <h4 className='aura-light-text'>Last API response</h4>
          <pre className='aura-code' style={{ color: '#334155' }}>{runtime.out}</pre>
        </div>
      </details>
    </section>
  </div>;
}

export default function App() {
  const surface = detectSurface();
  const runtime = useAuraRuntime(surface);
  return <>
    <AuraStyles />
    {surface === 'overlay' ? <OverlaySurface {...(runtime as any)} /> : <DashboardSurface {...(runtime as any)} />}
  </>;
}
