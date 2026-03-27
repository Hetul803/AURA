import { BACKEND_URL } from '../../shared/constants';

export async function healthcheck() {
  try {
    const r = await fetch(`${BACKEND_URL}/health`);
    return r.ok;
  } catch {
    return false;
  }
}

export async function getModelStatus() {
  const r = await fetch(`${BACKEND_URL}/models/status`);
  return r.json();
}

export async function getDemoStatus() {
  const r = await fetch(`${BACKEND_URL}/demo/status`);
  return r.json();
}

export async function sendCommand(text: string, choices: Record<string, string> = {}, useMacro = false, proactive?: Record<string, any>) {
  const r = await fetch(`${BACKEND_URL}/command`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, choices, use_macro: useMacro, proactive: proactive || null })
  });
  return r.json();
}

export async function startDemoScenario(scenarioId: string, heroTiming?: Record<string, any>) {
  const r = await fetch(`${BACKEND_URL}/demo/start`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ scenario_id: scenarioId, hero_timing: heroTiming || null }),
  });
  return r.json();
}

export async function captureAssistContext() {
  const r = await fetch(`${BACKEND_URL}/assist/context`, { method: 'POST' });
  return r.json();
}

export async function getAssistPersonalization(taskKind = 'summarize', capturedContext?: Record<string, any>) {
  const r = await fetch(`${BACKEND_URL}/assist/personalization`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ task_kind: taskKind, captured_context: capturedContext || null }),
  });
  return r.json();
}

export async function getAssistSuggestions(taskKind = 'summarize', capturedContext?: Record<string, any>) {
  const r = await fetch(`${BACKEND_URL}/assist/suggestions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ task_kind: taskKind, captured_context: capturedContext || null }),
  });
  return r.json();
}

export async function getProactiveSuggestions() {
  const r = await fetch(`${BACKEND_URL}/proactive/suggestions`);
  return r.json();
}

export function subscribeRun(runId: string, onEvent: (e: any) => void) {
  const es = new EventSource(`${BACKEND_URL}/events/stream/${runId}`);
  es.onmessage = (msg) => onEvent(JSON.parse(msg.data));
  es.onerror = () => onEvent({ run_id: runId, status: 'disconnected', type: 'stream_error', message: 'SSE disconnected' });
  return () => es.close();
}

export async function panicStop(runId: string) {
  await fetch(`${BACKEND_URL}/panic/${runId}`, { method: 'POST' });
}

export async function resumeRun(runId: string) {
  const r = await fetch(`${BACKEND_URL}/runs/${runId}/resume`, { method: 'POST' });
  return r.json();
}

export async function getRunState(runId: string) {
  const r = await fetch(`${BACKEND_URL}/runs/${runId}`);
  return r.json();
}

export async function approveRun(runId: string, text?: string) {
  const r = await fetch(`${BACKEND_URL}/runs/${runId}/approve`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text })
  });
  return r.json();
}

export async function retryRun(runId: string, feedback?: string) {
  const r = await fetch(`${BACKEND_URL}/runs/${runId}/retry`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ feedback })
  });
  return r.json();
}

export async function rejectRun(runId: string, reason?: string) {
  const r = await fetch(`${BACKEND_URL}/runs/${runId}/reject`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ reason })
  });
  return r.json();
}

export async function getGuardianEvents(runId?: string, limit = 20) {
  const params = new URLSearchParams();
  if (runId) params.set('run_id', runId);
  params.set('limit', String(limit));
  const r = await fetch(`${BACKEND_URL}/guardian/events?${params.toString()}`);
  return r.json();
}
