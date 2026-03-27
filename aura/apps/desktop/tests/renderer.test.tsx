import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../src/renderer/App';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { OnboardingState, PresenceState } from '../src/renderer/state/types';

const defaultPresence: PresenceState = {
  hotkey: 'Alt+Space',
  overlayEnabled: true,
  hotkeyRegistered: true,
  hotkeyError: '',
  overlayVisible: false,
  activeRunId: '',
  pendingApprovalRunId: '',
  lastRunStatus: 'idle',
};

const defaultOnboarding: OnboardingState = {
  completed: false,
  currentStep: 'welcome',
  startedAt: '2026-03-19T00:00:00Z',
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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.pushState({}, '', '/');
});

beforeEach(() => {
  vi.stubGlobal('EventSource', class {
    onmessage: ((evt: { data: string }) => void) | null = null;
    onerror: (() => void) | null = null;
    close() {}
  } as any);
});

function installDesktopBridge(overrides: Partial<PresenceState> = {}, onboardingOverrides: Partial<OnboardingState> = {}) {
  const listeners: Array<(state: PresenceState) => void> = [];
  let state: PresenceState = { ...defaultPresence, ...overrides };
  let onboardingState: OnboardingState = { ...defaultOnboarding, ...onboardingOverrides };
  const bridge = {
    openLogs: vi.fn(async () => '/tmp/logs'),
    getPresenceState: vi.fn(async () => state),
    updatePresenceState: vi.fn(async (patch: Partial<PresenceState>) => {
      state = { ...state, ...patch };
      listeners.forEach(listener => listener(state));
      return state;
    }),
    updateSettings: vi.fn(async (patch: Partial<PresenceState>) => {
      state = { ...state, ...patch };
      listeners.forEach(listener => listener(state));
      return state;
    }),
    getOnboardingState: vi.fn(async () => onboardingState),
    updateOnboardingState: vi.fn(async (patch: Partial<OnboardingState>) => {
      onboardingState = { ...onboardingState, ...patch, lastKnownReadiness: { ...onboardingState.lastKnownReadiness, ...(patch.lastKnownReadiness || {}) } };
      return onboardingState;
    }),
    completeOnboarding: vi.fn(async () => {
      onboardingState = { ...onboardingState, completed: true, currentStep: 'complete', completedAt: '2026-03-19T01:00:00Z' };
      return onboardingState;
    }),
    showOverlay: vi.fn(async () => {
      state = { ...state, overlayVisible: true };
      listeners.forEach(listener => listener(state));
      return state;
    }),
    hideOverlay: vi.fn(async () => {
      state = { ...state, overlayVisible: false };
      listeners.forEach(listener => listener(state));
      return state;
    }),
    showDashboard: vi.fn(async () => state),
    onPresenceState: vi.fn((callback: (next: PresenceState) => void) => {
      listeners.push(callback);
      return () => {
        const idx = listeners.indexOf(callback);
        if (idx >= 0) listeners.splice(idx, 1);
      };
    }),
  };
  (window as any).auraDesktop = bridge;
  return bridge;
}

function setupFetch(commandResponses: any[], runStateOverrides: Record<string, any> = {}, guardianEvents: any[] = []) {
  let i = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: any) => {
    if (url.includes('/health')) return { ok: true, json: async () => ({ ok: true }) } as any;
    if (url.includes('/models/status')) return { ok: true, json: async () => ({ selected_model: { provider: 'ollama', model: 'qwen2.5:3b' }, assist_drafting_ready: true, summary: 'Local model ready for real assist drafting.', limitations: [], demo_mode: true }) } as any;
    if (url.includes('/demo/status')) return { ok: true, json: async () => ({ enabled: true, scenarios: [{ id: 'email_reply', label: 'Email Reply', description: 'Mail demo', command: 'Draft a reply to this', task_kind: 'reply' }, { id: 'research_answer', label: 'Research Answer', description: 'Research demo', command: 'Research this and respond', task_kind: 'research_and_respond' }, { id: 'rewrite', label: 'Rewrite', description: 'Rewrite demo', command: 'Rewrite this better', task_kind: 'rewrite' }] }) } as any;
    if (url.includes('/assist/context')) return { ok: true, json: async () => ({ active_app: 'Notes', window_title: 'Draft', input_text: 'Captured text', input_source: 'clipboard_fallback', capture_path_used: 'clipboard_fallback', capture_method: { clipboard_preserved: true, clipboard_restored_after_capture: true } }) } as any;
    if (url.includes('/proactive/suggestions')) return { ok: true, json: async () => ({ captured_context: { active_app: 'Mail', window_title: 'Inbox', input_text: 'Captured text', input_source: 'clipboard_fallback', capture_path_used: 'clipboard_fallback', capture_method: { clipboard_preserved: true, clipboard_restored_after_capture: true } }, profile: { style_profile: { length_preference: { value: 'concise', confidence: 0.7 }, tone_preference: { value: 'polished', confidence: 0.8 }, warmth_preference: { value: 'neutral', confidence: 0.6 }, structure_preference: { value: 'answer_first', confidence: 0.65 }, research_tendency: { value: 'auto', confidence: 0.5 } }, approval_profile: { recommended_caution: 'elevated', edit_frequency: 0.33 } }, suggestions: [{ action: 'reply', label: 'Reply', command: 'Draft a reply to this', confidence: 0.88, reason: 'Current app/domain looks like email or messaging.', signals_used: [{ name: 'mail_surface', weight: 0.28 }] }] }) } as any;
    if (url.includes('/assist/personalization')) return { ok: true, json: async () => ({ style_profile: { length_preference: { value: 'concise', confidence: 0.7 }, tone_preference: { value: 'polished', confidence: 0.8 }, warmth_preference: { value: 'neutral', confidence: 0.6 }, structure_preference: { value: 'answer_first', confidence: 0.65 }, research_tendency: { value: 'auto', confidence: 0.5 } }, approval_profile: { recommended_caution: 'elevated', edit_frequency: 0.33 } }) } as any;
    if (url.includes('/preferences')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/memories')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/browser/sessions')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/storage/stats')) return { ok: true, json: async () => ({}) } as any;
    if (url.includes('/safety/events')) return { ok: true, json: async () => [] } as any;
    if (url.includes('/guardian/events')) return { ok: true, json: async () => guardianEvents } as any;
    if (url.match(/\/runs\/[^/]+$/)) {
      const runId = url.split('/').pop() || 'r1';
      return {
        ok: true,
        json: async () => ({
          status: 'awaiting_approval',
          approval_state: { status: 'pending', draft_text: 'Draft response' },
          captured_context: { input_text: 'Captured text', active_app: 'Mail', window_title: 'Inbox', input_source: 'clipboard_fallback', capture_path_used: 'clipboard_fallback', capture_method: { clipboard_preserved: true, clipboard_restored_after_capture: true } },
          pasteback_state: { target_validation_result: 'exact_match', paste_blocked_reason: null },
          assist: { generation: { provider: 'ollama', model: 'qwen2.5:3b', confidence: 0.82 } },
          draft_state: { style_hints: { tone: 'polished', length: 'concise' }, personalization_profile: { style_profile: { length_preference: { value: 'concise', confidence: 0.7 }, tone_preference: { value: 'polished', confidence: 0.8 }, warmth_preference: { value: 'neutral', confidence: 0.6 }, structure_preference: { value: 'answer_first', confidence: 0.65 }, research_tendency: { value: 'auto', confidence: 0.5 } }, approval_profile: { recommended_caution: 'elevated', edit_frequency: 0.33 } } },
          hero_timing: { phase: 'awaiting_approval', phase_label: 'Ready to review', detail: 'Draft ready for approval and paste-back.', durations_ms: { hotkey_to_overlay_visible: 90, overlay_submit_to_context_capture_complete: 120, model_request_duration: 280, approval_wait_duration: 0, pasteback_duration: null, total_run_duration: null }, marks: { overlay_visible_at: 1710800000 } },
          demo: { enabled: false, fallbacks: [] },
          ...runStateOverrides[runId],
        })
      } as any;
    }
    if (url.includes('/demo/start')) {
      const body = JSON.parse(options?.body || '{}');
      const runId = body.scenario_id === 'rewrite' ? 'demo-rewrite' : 'demo-run';
      const response = commandResponses[Math.min(i++, commandResponses.length - 1)] || {
        ok: false,
        run_id: runId,
        status: 'awaiting_approval',
        run_state: {
          status: 'awaiting_approval',
          approval_state: { status: 'pending', draft_text: body.scenario_id === 'rewrite' ? 'Improved paragraph' : 'Demo draft' },
          captured_context: { input_text: 'Demo input text', active_app: 'Mail', window_title: 'Demo', input_source: 'demo_fixture', capture_path_used: 'demo_fixture' },
          pasteback_state: { status: 'not_started' },
          demo: { enabled: true, scenario_id: body.scenario_id, scenario_label: body.scenario_id === 'rewrite' ? 'Rewrite' : 'Email Reply', fallbacks: [] },
          hero_timing: { phase: 'awaiting_approval', phase_label: 'Ready to review', detail: 'Draft ready for approval and paste-back.', durations_ms: { model_request_duration: 200 }, marks: { approval_wait_started_at: 1710800300 } }
        }
      };
      return { ok: true, json: async () => response } as any;
    }
    if (url.includes('/approve')) {
      const runId = url.split('/').at(-2) || 'r1';
      const approveResponse = runStateOverrides[runId]?.approve_response;
      return { ok: true, json: async () => (approveResponse || { ok: true, status: 'done' }) } as any;
    }
    if (url.includes('/retry')) return { ok: true, json: async () => ({ ok: true, status: 'awaiting_approval' }) } as any;
    if (url.includes('/reject')) return { ok: true, json: async () => ({ ok: true, status: 'rejected' }) } as any;
    if (url.includes('/resume')) return { ok: true, json: async () => ({ ok: true, status: 'running' }) } as any;
    const item = commandResponses[Math.min(i++, commandResponses.length - 1)] || { ok: true };
    if (options?.method === 'POST' && url.includes('/command')) return { ok: true, json: async () => item } as any;
    return { ok: true, json: async () => item } as any;
  }) as any);
}


function countFetchCalls(fragment: string) {
  return (fetch as any).mock.calls.filter((call: any[]) => String(call[0]).includes(fragment)).length;
}

describe('desktop renderer presence layer', () => {
  it('gates first run behind onboarding and can skip temporarily', async () => {
    installDesktopBridge();
    setupFetch([{ ok: true, run_id: 'r1' }]);

    render(<App />);
    await waitFor(() => expect(screen.getByText(/Getting started with AURA/)).toBeTruthy());
    fireEvent.click(screen.getByText('Skip for now'));
    await waitFor(() => expect(screen.getByText(/Resume onboarding/)).toBeTruthy());
  });

  it('resumes incomplete onboarding from the saved step', async () => {
    installDesktopBridge({}, { completed: false, currentStep: 'model' });
    setupFetch([{ ok: true, run_id: 'r1' }]);

    render(<App />);
    await waitFor(() => expect(screen.getByText(/Local model runtime/)).toBeTruthy());
  });

  it('persists starter preferences from onboarding', async () => {
    const bridge = installDesktopBridge({}, { completed: false, currentStep: 'preferences' });
    setupFetch([{ ok: true, run_id: 'r1' }]);

    render(<App />);
    await waitFor(() => expect(screen.getByText(/Pick a few starter defaults/)).toBeTruthy());
    fireEvent.change(screen.getByDisplayValue('Concise'), { target: { value: 'detailed' } });
    fireEvent.change(screen.getByDisplayValue('Polished'), { target: { value: 'direct' } });
    fireEvent.click(screen.getByText('Save starter preferences'));
    await waitFor(() => expect((fetch as any).mock.calls.some((call: any[]) => String(call[0]).includes('/preferences/writing.length?value=detailed'))).toBe(true));
    expect(bridge.updateOnboardingState).toHaveBeenCalled();
  });

  it('runs the guided first task from onboarding', async () => {
    installDesktopBridge({}, { completed: false, currentStep: 'first_task' });
    setupFetch([{ ok: false, run_id: 'guided-run', status: 'awaiting_approval' }], {
      'guided-run': {
        status: 'awaiting_approval',
        approval_state: { status: 'pending', draft_text: 'Draft response' },
      }
    });

    render(<App />);
    await waitFor(() => expect(screen.getByText(/Your first real task/)).toBeTruthy());
    fireEvent.click(screen.getByText('Start guided summary'));
    await waitFor(() => expect((fetch as any).mock.calls.some((call: any[]) => String(call[0]).includes('/command') && String(call[1]?.body || '').includes('"text":"Summarize this"'))).toBe(true));
  });

  it('preserves main dashboard behavior and shows presence status', async () => {
    installDesktopBridge({}, { completed: true, currentStep: 'complete' });
    setupFetch([{ ok: true, run_id: 'r1' }]);

    render(<App />);
    await waitFor(() => expect(screen.getByText(/Backend Connected/)).toBeTruthy());
    expect(screen.getByText(/Connected/)).toBeTruthy();
    expect(screen.getByText(/Presence/)).toBeTruthy();
    expect(screen.getByText(/Captured context/)).toBeTruthy();
    expect(screen.getByText(/clipboard_fallback/)).toBeTruthy();
    expect(screen.getByText(/Personalization/)).toBeTruthy();
  });

  it('opens overlay surface for quick command entry and run submission', async () => {
    window.history.pushState({}, '', '/?surface=overlay');
    const bridge = installDesktopBridge({ overlayVisible: true }, { completed: true, currentStep: 'complete' });
    setupFetch([{ ok: false, run_id: 'overlay-run', status: 'awaiting_approval' }]);

    render(<App />);
    await waitFor(() => expect(screen.getByText(/AURA Quick Invoke/)).toBeTruthy());
    expect(screen.getByText(/Current context/)).toBeTruthy();
    expect(screen.getByText(/Suggested next actions/)).toBeTruthy();
    expect(screen.getByText('Reply')).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText(/Ask AURA/), { target: { value: 'Summarize this' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    await waitFor(() => expect(bridge.updatePresenceState).toHaveBeenCalled());
    expect(screen.getByText(/Draft review/)).toBeTruthy();
  });

  it('shows demo entry points when demo mode is enabled and starts a scenario', async () => {
    window.history.pushState({}, '', '/?surface=overlay');
    installDesktopBridge({ overlayVisible: true }, { completed: true, currentStep: 'complete' });
    setupFetch([]);

    render(<App />);
    await waitFor(() => expect(screen.getByText(/Demo mode/)).toBeTruthy());
    fireEvent.click(screen.getByText('Try Demo: Email Reply'));
    await waitFor(() => expect(screen.getByDisplayValue('Demo draft')).toBeTruthy());
    expect((fetch as any).mock.calls.some((call: any[]) => String(call[0]).includes('/demo/start'))).toBe(true);
    expect(screen.getByText(/Active: Email Reply/)).toBeTruthy();
  });

  it('supports approval actions directly from the overlay', async () => {
    window.history.pushState({}, '', '/?surface=overlay');
    installDesktopBridge({ overlayVisible: true, activeRunId: 'r2', pendingApprovalRunId: 'r2' }, { completed: true, currentStep: 'complete' });
    setupFetch([{ ok: false, run_id: 'r2', status: 'awaiting_approval' }], {
      r2: {
        status: 'awaiting_approval',
        approval_state: { status: 'pending', draft_text: 'Draft response' },
        approve_response: { ok: true, status: 'done', run_state: { status: 'done', approval_state: { status: 'pasted', draft_text: 'Edited draft', final_text: 'Edited draft' }, pasteback_state: { status: 'pasted', target_validation_result: 'exact_match' }, hero_timing: { phase: 'completed', phase_label: 'Done', detail: 'Draft pasted back successfully.', durations_ms: { total_run_duration: 620, pasteback_duration: 90 }, marks: { run_completed_at: 1710800100 } } } },
      }
    });

    render(<App />);
    await waitFor(() => expect(screen.getByDisplayValue('Draft response')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('draft editor'), { target: { value: 'Edited draft' } });
    fireEvent.click(screen.getByText('Approve & Paste'));
    await waitFor(() => expect(screen.getByText(/Done/)).toBeTruthy());
  });

  it('shows demo fallback metadata after a demo copy fallback completes', async () => {
    window.history.pushState({}, '', '/?surface=overlay');
    installDesktopBridge({ overlayVisible: true, activeRunId: 'demo-run', pendingApprovalRunId: 'demo-run' }, { completed: true, currentStep: 'complete' });
    setupFetch([], {
      'demo-run': {
        status: 'awaiting_approval',
        approval_state: { status: 'pending', draft_text: 'Demo draft' },
        demo: { enabled: true, scenario_id: 'email_reply', scenario_label: 'Email Reply', fallbacks: ['copy_fallback'] },
        approve_response: { ok: true, status: 'done', run_state: { status: 'done', approval_state: { status: 'copied', draft_text: 'Demo draft', final_text: 'Demo draft' }, pasteback_state: { status: 'copied', target_validation_result: 'copied', paste_blocked_reason: 'target_drift_detected', demo_copy_fallback: true }, demo: { enabled: true, scenario_id: 'email_reply', scenario_label: 'Email Reply', fallbacks: ['copy_fallback'], used_copy_fallback: true }, hero_timing: { phase: 'completed', phase_label: 'Done', detail: 'Draft pasted back successfully.', durations_ms: { total_run_duration: 540 }, marks: { run_completed_at: 1710800100 } } } },
      }
    });

    render(<App />);
    await waitFor(() => expect(screen.getByDisplayValue('Demo draft')).toBeTruthy());
    fireEvent.click(screen.getByText('Approve & Paste'));
    await waitFor(() => expect(screen.getByText(/Fallbacks:/)).toBeTruthy());
    expect(screen.getAllByText(/copy_fallback/i).length).toBeGreaterThan(0);
  });


  it('reuses warm context state across quick overlay focus events', async () => {
    window.history.pushState({}, '', '/?surface=overlay');
    installDesktopBridge({ overlayVisible: true }, { completed: true, currentStep: 'complete' });
    setupFetch([{ ok: true, run_id: 'warm-run' }]);

    render(<App />);
    await waitFor(() => expect(screen.getByText(/AURA Quick Invoke/)).toBeTruthy());
    const proactiveCalls = countFetchCalls('/proactive/suggestions');
    const modelCalls = countFetchCalls('/models/status');
    window.dispatchEvent(new Event('focus'));
    await waitFor(() => expect(screen.getByText(/Current context/)).toBeTruthy());
    expect(countFetchCalls('/proactive/suggestions')).toBe(proactiveCalls);
    expect(countFetchCalls('/models/status')).toBe(modelCalls);
  });

  it('uses command run_state to avoid an immediate duplicate run fetch', async () => {
    window.history.pushState({}, '', '/?surface=overlay');
    installDesktopBridge({ overlayVisible: true }, { completed: true, currentStep: 'complete' });
    setupFetch([{ ok: false, run_id: 'fast-run', status: 'awaiting_approval', run_state: { status: 'awaiting_approval', approval_state: { status: 'pending', draft_text: 'Fast draft' }, pasteback_state: { status: 'not_started' }, hero_timing: { phase: 'awaiting_approval', phase_label: 'Ready to review', detail: 'Draft ready for approval and paste-back.', durations_ms: { model_request_duration: 240 }, marks: { approval_wait_started_at: 1710800200 } } } }]);

    render(<App />);
    await waitFor(() => expect(screen.getByText(/AURA Quick Invoke/)).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    await waitFor(() => expect(screen.getByDisplayValue('Fast draft')).toBeTruthy());
    expect(countFetchCalls('/runs/fast-run')).toBe(0);
  });

  it('runs immediately from a proactive suggestion click', async () => {
    window.history.pushState({}, '', '/?surface=overlay');
    const bridge = installDesktopBridge({ overlayVisible: true }, { completed: true, currentStep: 'complete' });
    setupFetch([{ ok: false, run_id: 'reply-run', status: 'awaiting_approval' }]);

    render(<App />);
    await waitFor(() => expect(screen.getByText('Reply')).toBeTruthy());
    fireEvent.click(screen.getByText('Reply'));
    await waitFor(() => expect(bridge.updatePresenceState).toHaveBeenCalled());
    expect((fetch as any).mock.calls.some((call: any[]) => String(call[0]).includes('/command') && String(call[1]?.body || '').includes('"suggestion_selected":"reply"'))).toBe(true);
  });

  it('reopens overlay with a pending approval run from shared presence state', async () => {
    window.history.pushState({}, '', '/?surface=overlay');
    installDesktopBridge({ overlayVisible: true, activeRunId: 'pending-run', pendingApprovalRunId: 'pending-run', lastRunStatus: 'awaiting_approval' }, { completed: true, currentStep: 'complete' });
    setupFetch([], {
      'pending-run': {
        status: 'awaiting_approval',
        approval_state: { status: 'pending', draft_text: 'Pending approval draft' },
      }
    });

    render(<App />);
    await waitFor(() => expect(screen.getByDisplayValue('Pending approval draft')).toBeTruthy());
    expect(screen.getByText(/Ready to review/)).toBeTruthy();
    expect(screen.getByText('pending-run')).toBeTruthy();
  });


  it('shows guardian warnings in the overlay when medium or high risk events exist', async () => {
    window.history.pushState({}, '', '/?surface=overlay');
    installDesktopBridge({ overlayVisible: true, activeRunId: 'r1' }, { completed: true, currentStep: 'complete' });
    setupFetch([{ ok: false, run_id: 'r1', status: 'awaiting_approval' }], {
      r1: {
        guardian_events: [{ run_id: 'r1', type: 'network_action', source: 'AURA', risk: 'high', summary: 'AURA performed an external research query.', explanation: 'The assist flow used a web search to gather outside context before drafting a response.', context: { target: 'search' } }],
      },
    }, []);

    render(<App />);
    await waitFor(() => expect(screen.getByText('Guardian warnings')).toBeTruthy());
    expect(screen.getAllByText(/external research query/i).length).toBeGreaterThan(0);
  });

  it('does not show a guardian banner when only low risk activity is present', async () => {
    installDesktopBridge({}, { completed: true, currentStep: 'complete' });
    setupFetch([{ ok: true, run_id: 'r1' }], {
      r1: {
        guardian_events: [{ run_id: 'r1', type: 'file_access', source: 'AURA', risk: 'low', summary: 'AURA read a local file.', explanation: 'This event is limited to filesystem actions AURA performed inside its own workflow.', context: { target: '/tmp/demo.txt' } }],
      },
    });

    render(<App />);
    await waitFor(() => expect(screen.getByText(/Captured context/)).toBeTruthy());
    expect(screen.queryByText(/Guardian note:/)).toBeNull();
  });

  it('surfaces hotkey registration failure clearly', async () => {
    installDesktopBridge({ hotkeyRegistered: false, hotkeyError: 'Failed to register global hotkey: Alt+Space' }, { completed: true, currentStep: 'complete' });
    setupFetch([{ ok: true, run_id: 'r3' }]);

    render(<App />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByText(/Hotkey error:/)).toBeTruthy();
  });

  it('can reopen onboarding after completion', async () => {
    installDesktopBridge({}, { completed: true, currentStep: 'complete', firstTaskCompleted: true });
    setupFetch([{ ok: true, run_id: 'r4' }]);

    render(<App />);
    await waitFor(() => expect(screen.getByText(/Reopen onboarding/)).toBeTruthy());
    fireEvent.click(screen.getByText('Reopen onboarding'));
    await waitFor(() => expect(screen.getByText(/Getting started with AURA/)).toBeTruthy());
  });
});
