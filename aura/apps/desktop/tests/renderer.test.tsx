import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../src/renderer/App';
import { afterEach, describe, it, expect, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mockFetch(sequence: any[]) {
  let i = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.includes('/health')) return { ok: true, json: async () => ({ ok: true }) } as any;
    const item = sequence[Math.min(i++, sequence.length - 1)];
    return { ok: true, json: async () => item } as any;
  }) as any);
}

describe('renderer', () => {
  it('shows connection status', async () => {
    mockFetch([{ ok: true, run_id: 'r1' }]);
    vi.stubGlobal('EventSource', class { onmessage: any; close() {} } as any);
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Backend:/)).toBeTruthy());
    expect(screen.getByText(/Connected/)).toBeTruthy();
  });

  it('renders NEEDS_USER banner and continue', async () => {
    mockFetch([{ ok: false, run_id: 'r2', status: 'needs_user' }, { ok: true, run_id: 'r2', steps: [] }]);
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
