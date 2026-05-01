import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../src/renderer/App';
import { afterEach, describe, it, expect, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function setupFetch(commandResponses: any[]) {
  let i = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: any) => {
    if (url.includes('/health')) return { ok: true, json: async () => ({ ok: true }) } as any;
    if (url.includes('/context/current')) return { ok: true, json: async () => ({ active_app: 'Notes', input_text: 'Captured text', input_source: 'clipboard_fallback', capture_path_used: 'clipboard_fallback', capture_method: { clipboard_preserved: true, clipboard_restored_after_capture: true } }) } as any;
    if (url.includes('/assist/context')) return { ok: true, json: async () => ({ active_app: 'Notes', input_text: 'Captured text', input_source: 'clipboard_fallback', capture_path_used: 'clipboard_fallback', capture_method: { clipboard_preserved: true, clipboard_restored_after_capture: true } }) } as any;
    if (url.includes('/tools')) return { ok: true, json: async () => [{ action_type: 'OS_PASTE', tool: 'os', risk_level: 'high', requires_approval: true }] } as any;
    if (url.includes('/devices')) return { ok: true, json: async () => [{ adapter_id: 'desktop-local', name: 'Local Desktop', surface: 'desktop', status: 'available' }] } as any;
    if (url.includes('/preferences')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/memories')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/browser/sessions')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/storage/stats')) return { ok: true, json: async () => ({}) } as any;
    if (url.includes('/safety/events')) return { ok: true, json: async () => [] } as any;
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
  it('shows connection status and capture preview', async () => {
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Personal AI operating layer/)).toBeTruthy());
    expect(screen.getByText(/Connected/)).toBeTruthy();
    expect(screen.getByText(/Captured Context/)).toBeTruthy();
    expect(screen.getByText(/Captured text/)).toBeTruthy();
    expect(screen.getByText(/clipboard_fallback/)).toBeTruthy();
  });

  it('renders approval ui and can approve draft', async () => {
    setupFetch([{ ok: false, run_id: 'r2', status: 'awaiting_approval' }]);
    vi.stubGlobal('EventSource', class {
      onmessage: any;
      constructor() { setTimeout(() => this.onmessage?.({ data: JSON.stringify({ run_id: 'r2', type: 'approval_required', status: 'awaiting_approval', message: 'Draft ready for approval.' }) }), 0); }
      close() {}
    } as any);

    render(<App />);
    fireEvent.change(screen.getByPlaceholderText('Type command'), { target: { value: 'Summarize this' } });
    fireEvent.click(screen.getByText('Run'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('draft editor'), { target: { value: 'Edited draft' } });
    fireEvent.click(screen.getByText('Approve & Paste'));
  });
});
