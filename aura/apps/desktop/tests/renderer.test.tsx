import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../src/renderer/App';
import { afterEach, describe, it, expect, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete (window as any).auraDesktop;
});

function setupFetch(commandResponses: any[]) {
  let i = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: any) => {
    if (url.includes('/health')) return { ok: true, json: async () => ({ ok: true }) } as any;
    if (url.includes('/context/current')) return { ok: true, json: async () => ({ active_app: 'Notes', input_text: 'Captured text', input_source: 'clipboard_fallback', capture_path_used: 'clipboard_fallback', capture_method: { clipboard_preserved: true, clipboard_restored_after_capture: true } }) } as any;
    if (url.includes('/assist/context')) return { ok: true, json: async () => ({ active_app: 'Notes', input_text: 'Captured text', input_source: 'clipboard_fallback', capture_path_used: 'clipboard_fallback', capture_method: { clipboard_preserved: true, clipboard_restored_after_capture: true } }) } as any;
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
    if (url.match(/\/runs\/[^/]+$/)) return { ok: true, json: async () => ({ approval_state: { status: 'pending', draft_text: 'Draft response' }, captured_context: { input_text: 'Captured text', active_app: 'Notes', input_source: 'clipboard_fallback', capture_path_used: 'clipboard_fallback', capture_method: { clipboard_preserved: true, clipboard_restored_after_capture: true } }, pasteback_state: { target_validation_result: 'exact_match', paste_blocked_reason: null } }) } as any;
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
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Personal AI operating layer/)).toBeTruthy());
    expect(screen.getAllByText(/AURA Core online/).length).toBeGreaterThan(0);
    expect(screen.getByText(/AURA sees/)).toBeTruthy();
    expect(screen.getByText(/Captured text/)).toBeTruthy();
    expect(screen.getByText(/Hotkey unavailable/)).toBeTruthy();
  });

  it('shows first-time onboarding and local model guidance', async () => {
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/First-Time Setup/)).toBeTruthy());
    expect(screen.getByText(/I am AURA, your personal AI operating layer/)).toBeTruthy();
    fireEvent.click(screen.getByText(/7. Local Model/));
    await waitFor(() => expect(screen.getByText(/Recommended local model/)).toBeTruthy());
    expect(screen.getByText(/Darwin/)).toBeTruthy();
    expect(screen.getByText(/Apple Silicon/)).toBeTruthy();
    expect(screen.getByText(/16 GB/)).toBeTruthy();
    expect(screen.getByText(/Missing \/ Stopped/)).toBeTruthy();
    expect(screen.getByLabelText('local model name')).toBeTruthy();
  });

  it('renders approval ui and can approve draft', async () => {
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
});
