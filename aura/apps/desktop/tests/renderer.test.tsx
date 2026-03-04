import { render, screen } from '@testing-library/react';
import App from '../src/renderer/App';
import { describe, it, expect, vi } from 'vitest';

describe('renderer', () => {
  it('shows overlay title and actions panel', () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ json: async () => ({ ok: true, run_id: 'r1' }) })) as any);
    vi.stubGlobal('EventSource', class {
      onmessage: any;
      constructor() { setTimeout(() => this.onmessage?.({ data: JSON.stringify({ run_id: 'r1', status: 'planned', name: 'x' }) }), 0); }
      close() {}
    } as any);
    render(<App />);
    expect(screen.getByText('AURA Overlay')).toBeTruthy();
    expect(screen.getByText('Actions')).toBeTruthy();
  });
});
