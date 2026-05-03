import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../src/renderer/App';
import { afterEach, describe, it, expect, vi } from 'vitest';

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

function setupFetch(commandResponses: any[], contextOverride?: any) {
  let i = 0;
  const context = contextOverride || { active_app: 'Notes', input_text: 'Captured text', input_source: 'clipboard_fallback', capture_path_used: 'clipboard_fallback', capture_method: { clipboard_preserved: true, clipboard_restored_after_capture: true } };
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: any) => {
    if (url.includes('/health')) return { ok: true, json: async () => ({ ok: true }) } as any;
    if (url.includes('/context/current')) return { ok: true, json: async () => context } as any;
    if (url.includes('/assist/context')) return { ok: true, json: async () => context } as any;
    if (url.includes('/tools')) return { ok: true, json: async () => [{ action_type: 'OS_PASTE', tool: 'os', risk_level: 'high', requires_approval: true }] } as any;
    if (url.includes('/devices')) return { ok: true, json: async () => [{ adapter_id: 'desktop-local', name: 'Local Desktop', surface: 'desktop', status: 'available' }] } as any;
    if (url.includes('/memory/items')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/workflows/suggestions')) return { ok: true, json: async () => [{ suggested_workflow_name: 'Clone repo locally', command_template: 'Clone this repo locally', task_type: 'github' }] } as any;
    if (url.includes('/workflows')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/preferences')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/memories')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/browser/sessions')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/storage/stats')) return { ok: true, json: async () => ({}) } as any;
    if (url.includes('/safety/events')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/guardian/status')) return { ok: true, json: async () => ({ status: 'protected', events: [] }) } as any;
    if (url.includes('/cost/summary')) return { ok: true, json: async () => ({ total_estimated_cost_usd: 0, estimated_savings_usd: 0, budget: {} }) } as any;
    if (url.includes('/cost/models')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/local-model/status')) return { ok: true, json: async () => ({
      hardware: { os: 'Darwin', arch: 'arm64', ram_gb: 16, apple_silicon: true },
      ollama: { installed: false, running: false, install_url: 'https://ollama.com/download' },
      available_models: [],
      recommendation: { model: 'gemma4:e4b-nvfp4', recommended_pull: 'gemma4:e4b-nvfp4', reason: 'compact default' },
      selected_model: { id: 'simple', model: 'simple', available: true },
      setup_steps: ['Install Ollama'],
      summary: 'Ollama is not installed.',
    }) } as any;
    if (url.includes('/models/select')) return { ok: true, json: async () => ({ ok: true, model_id: 'simple' }) } as any;
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

describe('renderer', () => {
  afterEach(() => localStorage.clear());

  it('shows connection status and capture preview', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Personal AI operating layer/)).toBeTruthy());
    expect(screen.getAllByText(/AURA Core online/).length).toBeGreaterThan(0);
    expect(screen.getByText(/AURA sees/)).toBeTruthy();
    expect(screen.getByText(/Captured text/)).toBeTruthy();
    expect(screen.getAllByText(/Hotkey unavailable/).length).toBeGreaterThan(0);
  });

  it('shows first-time onboarding and local model guidance', async () => {
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/First Launch Encounter/)).toBeTruthy());
    expect(screen.getByText(/Hello. I'm AURA/)).toBeTruthy();
    fireEvent.click(screen.getByText(/Local Model/));
    await waitFor(() => expect(screen.getByText(/Recommended local model/)).toBeTruthy());
    expect(screen.getByText(/Darwin/)).toBeTruthy();
    expect(screen.getByText(/Apple Silicon/)).toBeTruthy();
    expect(screen.getByText(/16 GB/)).toBeTruthy();
    expect(screen.getByText(/Missing \/ Stopped/)).toBeTruthy();
    expect(screen.getByLabelText('local model name')).toBeTruthy();
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

  it('renders Guardian, activity, memory, and launch flow cards', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/AURA Guardian/)).toBeTruthy());
    expect(screen.getByText(/Protected/)).toBeTruthy();
    expect(screen.getByText(/Examples until live events arrive/)).toBeTruthy();
    expect(screen.getByText(/Clone current repo/)).toBeTruthy();
    fireEvent.click(screen.getByText('Memory'));
    await waitFor(() => expect(screen.getByText(/Memory intelligence/)).toBeTruthy());
    expect(screen.getByText(/No memory updates yet/)).toBeTruthy();
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
    expect(screen.getByText(/Repair \/ retry/)).toBeTruthy();
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
    expect(screen.getByText(/CommandOrControl\+Shift\+Space brings AURA forward/)).toBeTruthy();
  });

  it('persists assistant rename during persona onboarding', async () => {
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/First Launch Encounter/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Rename Assistant/));
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
    fireEvent.click(screen.getByText(/Permissions/));
    await waitFor(() => expect(screen.getAllByText(/Accessibility/).length).toBeGreaterThan(0));
    expect(screen.getByText(/Never controls apps silently/)).toBeTruthy();
    fireEvent.click(screen.getByText(/Voice \+ Hotkey/));
    await waitFor(() => expect(screen.getAllByText(/Hotkey unavailable/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/enable Accessibility permission/i).length).toBeGreaterThan(0);
  });

  it('explains missing GitHub context before clone flow', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/What I can do right now/)).toBeTruthy());
    fireEvent.click(screen.getAllByRole('button', { name: /Show setup needed/i })[0]);
    await waitFor(() => expect(screen.getAllByText(/I don't see a GitHub repo yet/).length).toBeGreaterThan(0));
  });

  it('shows GitHub context actions when URL is supplied', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }], { active_app: 'Arc', browser_url: 'https://github.com/Hetul803/AURA', window_title: 'Hetul803/AURA: GitHub' });
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Clone this repo/)).toBeTruthy());
    expect(screen.getByText(/Summarize README/)).toBeTruthy();
    expect(screen.getAllByText(/GitHub context found/).length).toBeGreaterThan(0);
  });

  it('shows email context actions when mail context is supplied', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }], { active_app: 'Gmail', browser_url: 'https://mail.google.com/mail/u/0/#inbox', window_title: 'Gmail - Inbox', input_text: 'Can you send the proposal?' });
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Draft reply/)).toBeTruthy());
    expect(screen.getByText(/Summarize thread/)).toBeTruthy();
    expect(screen.getAllByText(/Email context found/).length).toBeGreaterThan(0);
  });

  it('keeps raw run ids out of the main home until Advanced is opened', async () => {
    localStorage.setItem('aura:onboarding-complete', '1');
    setupSpeech();
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/What should AURA do/)).toBeTruthy());
    expect(screen.queryByText(/Flow:/)).toBeNull();
    fireEvent.click(screen.getByText('Advanced'));
    await waitFor(() => expect(screen.getByText(/System, model, and backend internals/)).toBeTruthy());
  });
});
