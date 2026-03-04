import { BACKEND_URL } from '../../shared/constants';

export async function healthcheck() {
  try {
    const r = await fetch(`${BACKEND_URL}/health`);
    return r.ok;
  } catch {
    return false;
  }
}

export async function sendCommand(text: string, choices: Record<string, string> = {}, useMacro = false) {
  const r = await fetch(`${BACKEND_URL}/command`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, choices, use_macro: useMacro })
  });
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
