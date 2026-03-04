import { BACKEND_URL } from '../../shared/constants';

export async function sendCommand(text: string, choices: Record<string, string> = {}, useMacro = false) {
  const r = await fetch(`${BACKEND_URL}/command`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, choices, use_macro: useMacro })
  });
  return r.json();
}

export function subscribeRun(runId: string, onEvent: (e: any) => void) {
  const es = new EventSource(`${BACKEND_URL}/events/stream/${runId}`);
  es.onmessage = (msg) => onEvent(JSON.parse(msg.data));
  return () => es.close();
}

export async function panicStop(runId: string) {
  await fetch(`${BACKEND_URL}/panic`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ run_id: runId }) });
}
