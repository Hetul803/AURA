import { useEffect, useMemo, useState } from 'react';
import type { BackendState, ModelStatus, OnboardingState, OnboardingStepId, PresenceState } from '../state/types';
import { BACKEND_URL } from '../../shared/constants';

const STEPS: OnboardingStepId[] = ['welcome', 'presence', 'permissions', 'model', 'preferences', 'first_task', 'complete'];

type Props = {
  onboardingState: OnboardingState;
  presence: PresenceState;
  backendState: BackendState;
  modelStatus: ModelStatus | null;
  capturedContext: any;
  runId: string;
  runStatus: string;
  pendingApproval: boolean;
  draftText: string;
  setDraftText: (value: string) => void;
  finalText: string;
  approvalState: any;
  pasteState: any;
  setInput: (value: string) => void;
  refreshContext: () => Promise<void>;
  run: (choices?: Record<string, string>, useMacro?: boolean, proactiveSelection?: any, commandText?: string) => Promise<void>;
  approve: () => Promise<void>;
  updatePresenceSettings: (patch: Partial<PresenceState>) => Promise<void>;
  updateOnboardingState: (patch: Partial<OnboardingState>) => Promise<void>;
  completeOnboarding: () => Promise<void>;
  closeOnboarding: () => void;
};

function statusPill(status: 'ready' | 'needs_attention' | 'manual_check' | 'guidance') {
  const colors = {
    ready: '#14532d',
    needs_attention: '#7f1d1d',
    manual_check: '#78350f',
    guidance: '#1e3a8a',
  } as const;
  return {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 999,
    background: colors[status],
    color: 'white',
    fontSize: 12,
  };
}

export default function OnboardingFlow(props: Props) {
  const [lengthPreference, setLengthPreference] = useState('concise');
  const [tonePreference, setTonePreference] = useState('polished');
  const [usageMode, setUsageMode] = useState<'assist' | 'guided'>(props.onboardingState.usageMode);
  const [approvalMode, setApprovalMode] = useState<'strict' | 'balanced'>(props.onboardingState.approvalMode);
  const [proactiveEnabled, setProactiveEnabled] = useState<boolean>(props.onboardingState.proactiveEnabled);

  useEffect(() => {
    setUsageMode(props.onboardingState.usageMode);
    setApprovalMode(props.onboardingState.approvalMode);
    setProactiveEnabled(props.onboardingState.proactiveEnabled);
  }, [props.onboardingState]);

  const stepIndex = Math.max(0, STEPS.indexOf(props.onboardingState.currentStep));
  const backendReady = props.backendState.connection === 'Connected' || Boolean(props.modelStatus?.runtime_ready || props.modelStatus?.assist_drafting_ready);
  const modelReady = Boolean(props.modelStatus?.assist_drafting_ready);
  const captureWorking = Boolean(props.capturedContext?.capture_method || props.capturedContext?.input_text);
  const readiness = useMemo(() => ({
    hotkeyReady: props.presence.hotkeyRegistered,
    modelReady,
    permissionsChecked: captureWorking,
    firstTaskCompleted: props.onboardingState.firstTaskCompleted,
  }), [props.presence.hotkeyRegistered, modelReady, captureWorking, props.onboardingState.firstTaskCompleted]);

  const goToStep = async (step: OnboardingStepId) => {
    await props.updateOnboardingState({
      currentStep: step,
      lastKnownReadiness: {
        hotkeyReady: readiness.hotkeyReady,
        modelReady: readiness.modelReady,
        permissionsChecked: readiness.permissionsChecked,
      },
    });
  };

  const nextStep = async () => {
    const next = STEPS[Math.min(STEPS.length - 1, stepIndex + 1)];
    await goToStep(next);
  };

  const previousStep = async () => {
    const prev = STEPS[Math.max(0, stepIndex - 1)];
    await goToStep(prev);
  };

  const saveStarterPreferences = async () => {
    await Promise.all([
      fetch(`${BACKEND_URL}/preferences/writing.length?value=${encodeURIComponent(lengthPreference)}`, { method: 'POST' }),
      fetch(`${BACKEND_URL}/preferences/writing.tone?value=${encodeURIComponent(tonePreference)}`, { method: 'POST' }),
    ]);
    await props.updateOnboardingState({
      starterPreferencesSeeded: true,
      usageMode,
      approvalMode,
      proactiveEnabled,
      currentStep: 'first_task',
    });
  };

  const startFirstTask = async () => {
    await props.updateOnboardingState({ firstTaskRunId: props.runId || '', currentStep: 'first_task' });
    props.setInput('Summarize this');
    await props.run({}, false, undefined, 'Summarize this');
  };

  const markFirstTaskComplete = async () => {
    await props.updateOnboardingState({
      firstTaskCompleted: true,
      firstTaskRunId: props.runId,
      currentStep: 'complete',
      lastKnownReadiness: {
        hotkeyReady: readiness.hotkeyReady,
        modelReady: readiness.modelReady,
        permissionsChecked: readiness.permissionsChecked,
      },
    });
  };

  const renderStep = () => {
    switch (props.onboardingState.currentStep) {
      case 'welcome':
        return <>
          <h2>Welcome to AURA</h2>
          <p>AURA helps you capture text from another app, draft something useful with a local model, let you review it, and then paste or copy the result back safely.</p>
          <p><strong>This build is a Mac-first private alpha.</strong> It is intended for real desktop testing, but it still honestly depends on a local Python runtime, local backend dependencies, and local Ollama for real drafting.</p>
          <ul>
            <li>Use the overlay for quick cross-app help.</li>
            <li>Review before paste so the workflow stays trustworthy.</li>
            <li>Start with one small success, then let AURA learn your style over time.</li>
            <li>Unsigned builds may require manual Finder/Open approval on macOS.</li>
          </ul>
        </>;
      case 'presence':
        return <>
          <h2>Set up quick invoke</h2>
          <p>The overlay is the fastest way to use AURA across apps.</p>
          <div><strong>Current hotkey:</strong> {props.presence.hotkey}</div>
          <div><strong>Registration:</strong> <span style={statusPill(props.presence.hotkeyRegistered ? 'ready' : 'needs_attention')}>{props.presence.hotkeyRegistered ? 'Ready' : 'Needs attention'}</span></div>
          {props.presence.hotkeyError && <div role='alert' style={{ marginTop: 8 }}><strong>Issue:</strong> {props.presence.hotkeyError}</div>}
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            <button onClick={() => props.updatePresenceSettings({ hotkey: 'Alt+Space' })}>Use Alt+Space</button>
            <button onClick={() => props.updatePresenceSettings({ overlayEnabled: true })}>Enable Overlay</button>
            <button onClick={() => (window as any).auraDesktop?.showOverlay?.()}>Test Overlay</button>
          </div>
        </>;
      case 'permissions':
        return <>
          <h2>Permissions and trust</h2>
          <p>AURA needs honest, limited permissions to capture context and optionally paste results back.</p>
          <ul>
            <li>
              <strong>Automation / Accessibility:</strong> <span style={statusPill('manual_check')}>Manual check</span>
              <div>Cross-app capture and paste-back may require OS accessibility or automation permission on supported systems.</div>
            </li>
            <li>
              <strong>Clipboard / Context capture:</strong> <span style={statusPill(captureWorking ? 'ready' : 'manual_check')}>{captureWorking ? 'Working now' : 'Needs verification'}</span>
              <div>{captureWorking ? 'AURA can currently see capture metadata from your environment.' : 'Select or copy text in another app, then refresh to verify capture is working.'}</div>
            </li>
            <li>
              <strong>Browser context limits:</strong> <span style={statusPill('guidance')}>Guidance</span>
              <div>Browser title and URL context may be available, but AURA will only claim page-level context when it actually has it.</div>
            </li>
          </ul>
          <button onClick={props.refreshContext}>Refresh context check</button>
        </>;
      case 'model':
        return <>
          <h2>Local model runtime</h2>
          <div><strong>Backend status:</strong> <span style={statusPill(backendReady ? 'ready' : 'needs_attention')}>{backendReady ? 'Connected' : props.backendState.lifecycle}</span></div>
          <p>{props.backendState.message}</p>
          {!!props.backendState.detail && <pre style={{ whiteSpace: 'pre-wrap', background: '#f8fafc', borderRadius: 12, padding: 12 }}>{props.backendState.detail}</pre>}
          <div><strong>Selected provider:</strong> {props.modelStatus?.selected_model?.provider || '-'}</div>
          <div><strong>Selected model:</strong> {props.modelStatus?.selected_model?.model || '-'}</div>
          <div><strong>Drafting status:</strong> <span style={statusPill(modelReady ? 'ready' : 'needs_attention')}>{modelReady ? 'Ready for real assist drafting' : 'Not ready yet'}</span></div>
          <p>{props.modelStatus?.summary || 'Checking model runtime…'}</p>
          {!!props.modelStatus?.limitations?.length && <ul>{props.modelStatus.limitations.map((item: string) => <li key={item}>{item}</li>)}</ul>}
          {!!props.modelStatus?.setup_steps?.length && <>
            <strong>Next steps</strong>
            <ul>{props.modelStatus.setup_steps.map((item: string) => <li key={item}>{item}</li>)}</ul>
          </>}
        </>;
      case 'preferences':
        return <>
          <h2>Pick a few starter defaults</h2>
          <p>These only seed AURA’s behavior. It will still adapt from your actual approvals, edits, and usage.</p>
          <div style={{ display: 'grid', gap: 12 }}>
            <label>Usage mode
              <select value={usageMode} onChange={e => setUsageMode(e.target.value as 'assist' | 'guided')}>
                <option value='assist'>Quick assist</option>
                <option value='guided'>More guidance</option>
              </select>
            </label>
            <label>Default length
              <select value={lengthPreference} onChange={e => setLengthPreference(e.target.value)}>
                <option value='concise'>Concise</option>
                <option value='detailed'>Detailed</option>
              </select>
            </label>
            <label>Default tone
              <select value={tonePreference} onChange={e => setTonePreference(e.target.value)}>
                <option value='polished'>Polished</option>
                <option value='direct'>Direct</option>
              </select>
            </label>
            <label>Approval mode (informational for now)
              <select value={approvalMode} onChange={e => setApprovalMode(e.target.value as 'strict' | 'balanced')}>
                <option value='balanced'>Balanced review</option>
                <option value='strict'>Strict review</option>
              </select>
            </label>
            <label>
              <input type='checkbox' checked={proactiveEnabled} onChange={e => setProactiveEnabled(e.target.checked)} />
              Enable proactive suggestions
            </label>
          </div>
          <div style={{ marginTop: 12 }}>
            <button onClick={saveStarterPreferences}>Save starter preferences</button>
          </div>
        </>;
      case 'first_task':
        return <>
          <h2>Your first real task</h2>
          <ol>
            <li>Select or copy a short paragraph in another app.</li>
            <li>Come back here and refresh capture.</li>
            <li>Run a real summary through AURA.</li>
            <li>Review and approve the draft.</li>
          </ol>
          <div><strong>Capture detected:</strong> {props.capturedContext?.input_text ? 'Yes' : 'Not yet'}</div>
          <div><strong>Model ready:</strong> {modelReady ? 'Yes' : 'No'}</div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            <button onClick={props.refreshContext}>Refresh capture</button>
            <button onClick={startFirstTask} disabled={!backendReady || !modelReady || !props.capturedContext?.input_text}>Start guided summary</button>
          </div>
          {!backendReady && <p role='alert'>AURA cannot complete the first task until the packaged backend is healthy.</p>}
          {!modelReady && <p role='alert'>AURA cannot complete a real drafting task until the local model runtime is ready.</p>}
          {props.runId && <div style={{ marginTop: 16 }}>
            <div><strong>Run status:</strong> {props.runStatus}</div>
            {props.draftText && <>
              <textarea aria-label='onboarding draft editor' value={props.draftText} onChange={e => props.setDraftText(e.target.value)} rows={8} style={{ width: '100%', marginTop: 8 }} />
              {props.pendingApproval && <button style={{ marginTop: 8 }} onClick={props.approve}>Approve guided task</button>}
            </>}
            {!!props.finalText && <div style={{ marginTop: 8 }}>
              <button onClick={async () => {
                await navigator.clipboard.writeText(props.finalText);
                await markFirstTaskComplete();
              }}>Copy result and mark success</button>
            </div>}
            {props.pasteState?.status === 'pasted' && <div style={{ marginTop: 8 }}>
              <button onClick={markFirstTaskComplete}>Mark pasted result as success</button>
            </div>}
          </div>}
        </>;
      case 'complete':
        return <>
          <h2>You’re ready to use AURA</h2>
          <ul>
            <li>Backend: {backendReady ? 'healthy' : 'needs attention'}</li>
            <li>Hotkey: {readiness.hotkeyReady ? 'ready' : 'needs attention'}</li>
            <li>Local model: {readiness.modelReady ? 'ready' : 'missing / not ready'}</li>
            <li>Capture check: {readiness.permissionsChecked ? 'working' : 'still verify permissions'}</li>
            <li>First task: {props.onboardingState.firstTaskCompleted ? 'completed' : 'not completed yet'}</li>
          </ul>
          <p>You can reopen onboarding later from the main app if you want to revisit setup.</p>
        </>;
      default:
        return null;
    }
  };

  return <section style={{ border: '1px solid #cbd5e1', borderRadius: 12, padding: 16, marginBottom: 16, background: '#f8fafc' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
      <div>
        <strong>Getting started with AURA</strong>
        <div style={{ fontSize: 13, color: '#475569' }}>Step {stepIndex + 1} of {STEPS.length}</div>
      </div>
      <button onClick={props.closeOnboarding}>Skip for now</button>
    </div>
    {renderStep()}
    <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
      <button onClick={previousStep} disabled={stepIndex === 0}>Back</button>
      {props.onboardingState.currentStep !== 'preferences' && props.onboardingState.currentStep !== 'first_task' && props.onboardingState.currentStep !== 'complete' && (
        <button onClick={nextStep}>Continue</button>
      )}
      {props.onboardingState.currentStep === 'complete' && (
        <button onClick={async () => {
          await props.completeOnboarding();
          props.closeOnboarding();
        }}>Finish onboarding</button>
      )}
    </div>
  </section>;
}
