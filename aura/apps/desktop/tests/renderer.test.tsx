import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../src/renderer/App';
import { afterEach, describe, it, expect, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function setupFetch(commandResponses: any[]) {
  let i = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.includes('/health')) return { ok: true, json: async () => ({ ok: true }) } as any;
    if (url.includes('/preferences')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/memories')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/macros')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/browser/sessions')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/storage/stats')) return { ok: true, json: async () => ({}) } as any;
    if (url.includes('/safety/events')) return { ok: true, json: async () => [] } as any;
    const item = commandResponses[Math.min(i++, commandResponses.length - 1)] || { ok: true };
    return { ok: true, json: async () => item } as any;
  }) as any);
}

describe('renderer', () => {
  it('shows connection status', async () => {
    setupFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Backend:/)).toBeTruthy());
    expect(screen.getByText(/Connected/)).toBeTruthy();
  });

  it('renders NEEDS_USER banner and continue', async () => {
    setupFetch([{ ok: false, run_id: 'r2', status: 'needs_user' }, { ok: true, run_id: 'r2', steps: [] }]);
    vi.stubGlobal('EventSource', class {
      onmessage: any;
      constructor() { setTimeout(() => this.onmessage?.({ data: JSON.stringify({ run_id: 'r2', type: 'needs_user', status: 'needs_user', message: 'Login required' }) }), 0); }
      close() {}
    } as any);

    render(<App />);
    fireEvent.change(screen.getByPlaceholderText('Type command'), { target: { value: 'open gmail' } });
    fireEvent.click(screen.getByText('Run'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    fireEvent.click(screen.getByText('Continue'));
  });
});
