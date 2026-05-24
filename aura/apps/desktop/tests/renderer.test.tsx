import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../src/renderer/App';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete (window as any).auraDesktop;
});

function setupSpeech() {
  vi.stubGlobal('SpeechSynthesisUtterance', class {
    text: string;
    constructor(text: string) { this.text = text; }
  } as any);
  Object.defineProperty(window, 'speechSynthesis', {
    value: { cancel: vi.fn(), speak: vi.fn() },
    configurable: true,
  });
}

function setupFetch(commandResponses: any[], contextOverride?: any, localModelOverride?: any, guardianOverride?: any) {
  let i = 0;
  const context = contextOverride || { active_app: 'Notes', input_text: 'Captured text', input_source: 'clipboard_fallback', capture_path_used: 'clipboard_fallback', capture_method: { clipboard_preserved: true, clipboard_restored_after_capture: true } };
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: any) => {
    if (url.includes('/health')) return { ok: true, json: async () => ({ ok: true }) } as any;
    if (url.includes('/context/current')) return { ok: true, json: async () => context } as any;
    if (url.includes('/assist/context')) return { ok: true, json: async () => context } as any;
    if (url.includes('/user-tools/privacy-check')) return { ok: true, json: async () => ({ destination: 'ChatGPT', labels: ['email'], redacted: true, requires_approval: true, summary: 'Guardian redacted contact details before handoff.' }) } as any;
    if (url.includes('/user-tools')) return { ok: true, json: async () => [{ id: 'chatgpt', name: 'ChatGPT', status: 'manual_handoff' }, { id: 'claude', name: 'Claude', status: 'manual_handoff' }, { id: 'codex', name: 'Codex', status: 'manual_handoff' }] } as any;
    if (url.includes('/tools')) return { ok: true, json: async () => [{ action_type: 'OS_PASTE', tool: 'os', risk_level: 'high', requires_approval: true }] } as any;
    if (url.includes('/devices')) return { ok: true, json: async () => [{ adapter_id: 'desktop-local', name: 'Local Desktop', surface: 'desktop', status: 'available' }] } as any;
    if (url.includes('/memory/search')) return { ok: true, json: async () => [{ memory_id: 'm1', memory_key: 'workspace.preference', value: 'prefers ~/AURA/workspaces', score: 0.8 }] } as any;
    if (url.includes('/memory/items')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/workflows/suggestions')) return { ok: true, json: async () => [{ suggested_workflow_name: 'Clone repo locally', command_template: 'Clone this repo locally', task_type: 'github' }] } as any;
    if (url.includes('/workflows')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/preferences')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/memories')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/browser/sessions')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/storage/stats')) return { ok: true, json: async () => ({}) } as any;
    if (url.includes('/safety/events')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/guardian/status')) return { ok: true, json: async () => (guardianOverride || { status: 'protected', events: [] }) } as any;
    if (url.includes('/cost/summary')) return { ok: true, json: async () => ({ total_estimated_cost_usd: 0, estimated_savings_usd: 0, budget: {} }) } as any;
    if (url.includes('/cost/models')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/local-model/status')) return { ok: true, json: async () => (localModelOverride || {
      hardware: { os: 'Darwin', arch: 'arm64', ram_gb: 16, apple_silicon: true },
      ollama: { installed: false, running: false, install_url: 'https://ollama.com/download' },
      available_models: [],
      recommendation: {
        model: 'gemma4:e4b-nvfp4',
        recommended_pull: 'gemma4:e4b-nvfp4',
        reason: 'Gemma 4 compact fits this Mac.',
        choices: [
          { id: 'gemma4:e4b-nvfp4', model: 'gemma4:e4b-nvfp4', label: 'Gemma 4 compact', min_ram_gb: 8, role: 'private/simple tasks', installed: false, available_for_hardware: true, recommended: true, status: 'recommended' },
          { id: 'gemma4:latest', model: 'gemma4:latest', label: 'Gemma 4 balanced', min_ram_gb: 16, role: 'better local drafting', installed: false, available_for_hardware: true, recommended: false, status: 'available' },
          { id: 'simple', model: 'simple', label: 'Skip local model for now', min_ram_gb: 0, role: 'fallback', installed: true, available_for_hardware: true, recommended: false, status: 'fallback' },
        ],
      },
      selected_model: { id: 'simple', model: 'simple', available: true },
      setup_steps: ['Install Ollama'],
      summary: 'Ollama is not installed.',
    }) } as any;
    if (url.includes('/models/select')) return { ok: true, json: async () => ({ ok: true, model_id: 'simple' }) } as any;
    if (url.includes('/local-model/start')) return { ok: true, json: async () => ({ ok: true, status: 'started', command: 'ollama serve' }) } as any;
    if (url.includes('/local-model/pull')) return { ok: true, json: async () => ({ ok: false, requires_approval: true }) } as any;
    if (url.includes('/profile/status') && options?.method === 'PATCH') return { ok: true, json: async () => ({ metadata: {}, usage_limits: {} }) } as any;
    if (url.match(/\/runs\/[^/]+$/)) return { ok: true, json: async () => ({ approval_state: { status: 'pending', draft_text: 'Draft response' }, captured_context: context, pasteback_state: { target_validation_result: 'exact_match', paste_blocked_reason: null } }) } as any;
    if (url.includes('/approve')) return { ok: true, json: async () => ({ ok: true, status: 'done' }) } as any;
    if (url.includes('/retry')) return { ok: true, json: async () => ({ ok: true, status: 'awaiting_approval' }) } as any;
    if (url.includes('/reject')) return { ok: true, json: async () => ({ ok: true, status: 'rejected' }) } as any;
    const item = commandResponses[Math.min(i++, commandResponses.length - 1)] || { ok: true };
    if (options?.method === 'POST' && url.includes('/command')) return { ok: true, json: async () => item } as any;
    return { ok: true, json: async () => item } as any;
  }) as any);
}

async function advanceOnboardingTo(text: RegExp | string) {
  for (let i = 0; i < 10; i += 1) {
    if (screen.queryAllByText(text).length) return;
    fireEvent.click(screen.getByText('Continue'));
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  await waitFor(() => expect(screen.queryAllByText(text).length).toBeGreaterThan(0));
}

describe('renderer', () => {
  afterEach(() => localStorage.clear());

  it('ships the one-command start script and root scripts', () => {
    let root = process.cwd();
    for (let i = 0; i < 6 && !existsSync(join(root, 'start-aura.sh')); i += 1) root = dirname(root);
    const scriptPath = join(root, 'start-aura.sh');
    const packagePath = join(root, 'package.json');
    expect(existsSync(scriptPath)).toBe(true);
    expect(statSync(scriptPath).mode & 0o111).toBeGreaterThan(0);
    const script = readFileSync(scriptPath, 'utf8');
    expect(script).toContain('scripts/aura-dev.sh');
    const pkg = JSON.parse(readFileSync(packagePath, 'utf8'));
    expect(pkg.scripts['aura:start']).toContain('scripts/aura-dev.sh');
    expect(pkg.scripts['aura:package']).toContain('build-mac-dmg.sh');
  });

  it('shows connection status and capture preview', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/AI operating layer/)).toBeTruthy());
    expect(screen.getAllByText(/AURA Core online/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/AURA sees/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Captured text/)).toBeTruthy();
    expect(screen.getAllByText(/Hotkey needs Accessibility|Hotkey setup/).length).toBeGreaterThan(0);
  });

  it('shows first-time onboarding and local model guidance', async () => {
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Welcome to AURA/)).toBeTruthy());
    expect(screen.getByText(/Your AI is here/)).toBeTruthy();
    expect((window.speechSynthesis.speak as any).mock.calls.length).toBeGreaterThan(0);
    await advanceOnboardingTo(/Local model setup is optional/);
    await waitFor(() => expect(screen.getByText(/Recommended local model/)).toBeTruthy());
    expect(screen.getByText(/Darwin/)).toBeTruthy();
    expect(screen.getByText(/Apple Silicon/)).toBeTruthy();
    expect(screen.getAllByText(/16 GB/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Missing \/ Stopped/)).toBeTruthy();
    expect(screen.getByText(/Choose model size/)).toBeTruthy();
    expect(screen.getAllByText(/Gemma 4 compact/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Skip local model for now/)).toBeTruthy();
  });

  it('forces onboarding before home and can restart onboarding later', async () => {
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    const { unmount } = render(<App />);
    await waitFor(() => expect(screen.getByText(/Welcome to AURA/)).toBeTruthy());
    expect(screen.queryByText(/Restart onboarding/)).toBeNull();
    unmount();
    cleanup();
    localStorage.setItem('aura:onboarding-complete', '1');
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Restart onboarding/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Restart onboarding/));
    await waitFor(() => expect(screen.getByText(/Welcome to AURA/)).toBeTruthy());
  });

  it('can finish onboarding when hardware or model detection fails', async () => {
    setupSpeech();
    vi.stubGlobal('fetch', vi.fn(async (url: string, options?: any) => {
      if (url.includes('/local-model/status')) throw new Error('model detection failed');
      if (url.includes('/health')) return { ok: true, json: async () => ({ ok: true }) } as any;
      if (url.includes('/profile/status') && options?.method === 'PATCH') return { ok: true, json: async () => ({ metadata: {}, usage_limits: {} }) } as any;
      return { ok: true, json: async () => [] } as any;
    }) as any);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Welcome to AURA/)).toBeTruthy());
    fireEvent.click(screen.getByText('Enter command layer'));
    await waitFor(() => expect(screen.getByText(/AI operating layer/)).toBeTruthy());
  });

  it('shows model pull approval and persists selected fallback', async () => {
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await advanceOnboardingTo(/Local model setup is optional/);
    await waitFor(() => expect(screen.getAllByText(/Approve download/).length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText(/Use fallback/));
    await waitFor(() => expect((fetch as any).mock.calls.some((call: any[]) => String(call[0]).includes('/models/select?model_id=simple'))).toBe(true));
  });

  it('renders approval ui and can approve draft', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: false, run_id: 'r2', status: 'awaiting_approval' }]);
    vi.stubGlobal('EventSource', class {
      onmessage: any;
      constructor() { setTimeout(() => this.onmessage?.({ data: JSON.stringify({ run_id: 'r2', type: 'approval_required', status: 'awaiting_approval', message: 'Draft ready for approval.' }) }), 0); }
      close() {}
    } as any);

    render(<App />);
    fireEvent.change(screen.getByLabelText('command input'), { target: { value: 'Summarize this' } });
    fireEvent.click(screen.getByRole('button', { name: 'run command' }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('draft editor'), { target: { value: 'Edited draft' } });
    fireEvent.click(screen.getByText('Approve & Paste'));
  });

  it('renders presence-first home and Guardian Watchtower without dashboard panels', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Guardian Watchtower|Watchtower active/)).toBeTruthy());
    expect(screen.getByText(/Conversation/)).toBeTruthy();
    expect(screen.getByText(/Watching shell\/file actions/)).toBeTruthy();
    expect(screen.getByText(/Website permission monitoring is planned/)).toBeTruthy();
    expect(screen.queryByText(/Memory intelligence/)).toBeNull();
    fireEvent.click(screen.getByText(/Advanced \/ Diagnostics/));
    await waitFor(() => expect(screen.getAllByText(/Memory/).length).toBeGreaterThan(0));
    fireEvent.click(screen.getByText(/^Memory$/));
    await waitFor(() => expect(screen.getByText(/Memory inbox is ready/)).toBeTruthy());
    expect(screen.getAllByText(/Memory inbox is ready/).length).toBeGreaterThan(0);
  });

  it('renders rich Guardian events in the main action stream', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }], undefined, undefined, {
      status: 'protected',
      events: [{
        severity: 'blocked',
        title: 'Guardian blocked remote shell installer.',
        explanation: 'This command pipes a remote script into your shell.',
        action_required: 'Choose a safer command.',
        risk: 'blocked',
      }],
    });
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/blocked remote shell installer/)).toBeTruthy());
    expect(screen.getByText(/pipes a remote script into your shell/)).toBeTruthy();
  });

  it('shows backend fallback when health check fails', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/health')) throw new Error('connection refused');
      return { ok: true, json: async () => [] } as any;
    }) as any);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getAllByText(/AURA Core disconnected/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/Repair Backend/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/cannot reach AURA Core/).length).toBeGreaterThan(0);
  });

  it('renders hotkey active status from desktop bridge', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    (window as any).auraDesktop = {
      getHotkeyStatus: async () => ({ ok: true, accelerator: 'CommandOrControl+Shift+Space' }),
      onHotkey: () => () => undefined,
      openLogs: async () => '/tmp/aura',
    };
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Hotkey active/)).toBeTruthy());
    expect(screen.getByText(/Restart onboarding/)).toBeTruthy();
  });

  it('uses desktop voice fallback for audible speech test', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    const speakText = vi.fn(async () => ({ ok: true, status: 'speaking', provider: 'macos_say' }));
    (window as any).auraDesktop = {
      speakText,
      getHotkeyStatus: async () => ({ ok: true, accelerator: 'Alt+Space' }),
      onHotkey: () => () => undefined,
    };
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Test AURA voice/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Test AURA voice/));
    await waitFor(() => expect(speakText).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText(/macos_say/)).toBeTruthy());
  });

  it('renders overlay control and asks Electron to show it', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    const showOverlay = vi.fn(async () => ({ ok: true, visible: true }));
    (window as any).auraDesktop = {
      showOverlay,
      getHotkeyStatus: async () => ({ ok: true, accelerator: 'Alt+Space' }),
      onHotkey: () => () => undefined,
    };
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Show overlay/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Show overlay/));
    await waitFor(() => expect(showOverlay).toHaveBeenCalled());
  });

  it('persists assistant rename during persona onboarding', async () => {
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Welcome to AURA/)).toBeTruthy());
    await advanceOnboardingTo(/yours to name/);
    fireEvent.change(screen.getByLabelText('assistant name'), { target: { value: 'Alice' } });
    fireEvent.click(screen.getByText('Save name'));
    await waitFor(() => expect(localStorage.getItem('aura:assistant-name')).toBe('Alice'));
    expect(screen.getByText(/Good choice. I'm Alice now/)).toBeTruthy();
  });

  it('shows guided permission cards and hotkey unavailable explanation', async () => {
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await advanceOnboardingTo(/Give me permission only where you want control/);
    await waitFor(() => expect(screen.getAllByText(/Accessibility/).length).toBeGreaterThan(0));
    expect(screen.getByText(/Never controls apps silently/)).toBeTruthy();
    await waitFor(() => expect(screen.getAllByText(/Hotkey unavailable/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/enable Accessibility permission/i).length).toBeGreaterThan(0);
  });

  it('renders voice unsupported fallback honestly', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    Object.defineProperty(window, 'SpeechRecognition', { value: undefined, configurable: true });
    Object.defineProperty(window, 'webkitSpeechRecognition', { value: undefined, configurable: true });
    render(<App />);
    await waitFor(() => expect(screen.getByText(/AI operating layer/)).toBeTruthy());
    fireEvent.click(screen.getByText('Mic'));
    await waitFor(() => expect(screen.getAllByText(/Voice input is not available in this build/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/You can still type commands/).length).toBeGreaterThan(0);
  });

  it('submits a transcribed push-to-talk command', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }], { active_app: 'Arc', browser_url: 'https://github.com/Hetul803/AURA', window_title: 'Hetul803/AURA: GitHub' });
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    class FakeRecognition {
      lang = '';
      continuous = false;
      interimResults = false;
      onresult: any;
      onerror: any;
      onend: any;
      start() {
        const finalResult: any = [{ transcript: 'hey aura clone this repo' }];
        finalResult.isFinal = true;
        setTimeout(() => this.onresult?.({ results: [finalResult] }), 0);
      }
      stop() { this.onend?.(); }
    }
    Object.defineProperty(window, 'webkitSpeechRecognition', { value: FakeRecognition, configurable: true });
    render(<App />);
    await waitFor(() => expect(screen.getByText(/clone this repo/)).toBeTruthy());
    fireEvent.click(screen.getByText('Mic'));
    await waitFor(() => expect((fetch as any).mock.calls.some((call: any[]) => {
      const body = call[1]?.body ? JSON.parse(call[1].body) : {};
      return String(call[0]).includes('/command') && body.text === 'Clone this repo locally';
    })).toBe(true));
  });

  it('explains missing GitHub context before clone flow', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/AI operating layer/)).toBeTruthy());
    fireEvent.change(screen.getByLabelText('command input'), { target: { value: 'clone this repo' } });
    fireEvent.click(screen.getByRole('button', { name: 'run command' }));
    await waitFor(() => expect(screen.getAllByText(/I don't see a GitHub repo yet/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/needs GitHub context/).length).toBeGreaterThan(0);
  });

  it('retrieves useful memory before command execution', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r-memory' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/AI operating layer/)).toBeTruthy());
    fireEvent.change(screen.getByLabelText('command input'), { target: { value: 'build app' } });
    fireEvent.click(screen.getByRole('button', { name: 'run command' }));
    await waitFor(() => expect((fetch as any).mock.calls.some((call: any[]) => String(call[0]).includes('/memory/search'))).toBe(true));
    await waitFor(() => expect(screen.getByText(/I remembered workspace preference/)).toBeTruthy());
  });

  it('shows GitHub context actions when URL is supplied', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }], { active_app: 'Arc', browser_url: 'https://github.com/Hetul803/AURA', window_title: 'Hetul803/AURA: GitHub' });
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getAllByText(/GitHub repo/).length).toBeGreaterThan(0));
    expect(screen.getByText(/github.com\/Hetul803\/AURA/)).toBeTruthy();
    expect(screen.getByText(/What AURA can do right now/)).toBeTruthy();
    expect(screen.getAllByText(/Clone this repo/).length).toBeGreaterThan(0);
  });

  it('shows email context actions when mail context is supplied', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }], { active_app: 'Gmail', browser_url: 'https://mail.google.com/mail/u/0/#inbox', window_title: 'Gmail - Inbox', input_text: 'Can you send the proposal?' });
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getAllByText(/Email thread/).length).toBeGreaterThan(0));
    expect(screen.getByText(/Can you send the proposal/)).toBeTruthy();
  });

  it('explains missing email context before reply flow', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/AI operating layer/)).toBeTruthy());
    fireEvent.change(screen.getByLabelText('command input'), { target: { value: 'Reply to this email' } });
    fireEvent.click(screen.getByRole('button', { name: 'run command' }));
    await waitFor(() => expect(screen.getAllByText(/I don't see an email thread yet/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/needs email context/).length).toBeGreaterThan(0);
  });

  it('reacts to blocked Guardian events with blocked presence state', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: false, run_id: 'r-blocked', status: 'blocked', run_state: { status: 'blocked' } }]);
    vi.stubGlobal('EventSource', class {
      onmessage: any;
      constructor() {
        setTimeout(() => this.onmessage?.({ data: JSON.stringify({
          run_id: 'r-blocked',
          type: 'guardian_event',
          status: 'blocked',
          severity: 'blocked',
          title: 'Guardian blocked dangerous shell command.',
          explanation: 'This command can delete files.',
          action_required: 'Edit the command.',
        }) }), 0);
      }
      close() {}
    } as any);
    render(<App />);
    fireEvent.change(screen.getByLabelText('command input'), { target: { value: 'Run shell command: rm -rf ~' } });
    fireEvent.click(screen.getByRole('button', { name: 'run command' }));
    await waitFor(() => expect(screen.getByText(/Guardian blocked that/)).toBeTruthy());
    expect(screen.getAllByText(/blocked dangerous shell command/).length).toBeGreaterThan(0);
  });

  it('build app voice or card path creates coding job feedback', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r-build', steps: [{ result: { result: { agent_job: { job_dir: '/tmp/aura-job' } } } }] }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/AI operating layer/)).toBeTruthy());
    fireEvent.click(screen.getByText(/build app/));
    fireEvent.click(screen.getByRole('button', { name: 'run command' }));
    await waitFor(() => expect(screen.getAllByText(/Done. I created a coding job at \/tmp\/aura-job/).length).toBeGreaterThan(0));
  });

  it('keeps raw run ids out of the main home until Advanced is opened', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/AI operating layer/)).toBeTruthy());
    expect(screen.queryByText(/Flow:/)).toBeNull();
    fireEvent.click(screen.getByText(/Advanced \/ Diagnostics/));
    await waitFor(() => expect(screen.getByText(/Diagnostics \/ Freshness/)).toBeTruthy());
    expect(screen.getByText(/Build ID:/)).toBeTruthy();
  });

  it('shows memory continuity and AI handoff privacy checks for real users', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/What AURA knows about me/)).toBeTruthy());
    expect(screen.getByText(/Teach AURA a preference/)).toBeTruthy();
    expect(screen.getByText(/Use AURA with other AI tools/)).toBeTruthy();
    fireEvent.click(screen.getAllByText(/Privacy check/)[0]);
    await waitFor(() => expect(screen.getByText(/Guardian Privacy Check/)).toBeTruthy());
    expect(screen.getByText(/Approval required before handoff/)).toBeTruthy();
  });

  it('shows honest OS Guardian Foundation in Advanced', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/AI operating layer/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Advanced \/ Diagnostics/));
    fireEvent.click(screen.getAllByText(/OS Guardian Foundation/)[0]);
    await waitFor(() => expect(screen.getByText(/Honest protection map/)).toBeTruthy());
    expect(screen.getByText(/AURA-managed actions today/)).toBeTruthy();
    expect(screen.getByText(/Endpoint Security native extension/)).toBeTruthy();
  });
});
