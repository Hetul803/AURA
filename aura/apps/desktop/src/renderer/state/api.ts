import { BACKEND_URL } from '../../shared/constants';

export async function healthcheck() {
  try {
    const r = await fetch(`${BACKEND_URL}/health`);
    return r.ok;
  } catch {
    return false;
  }
}

export async function sendCommand(text: string, choices: Record<string, string> = {}, useMacro = false, context?: any) {
  const r = await fetch(`${BACKEND_URL}/command`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, choices, use_macro: useMacro, context })
  });
  return r.json();
}

export async function captureAssistContext() {
  const r = await fetch(`${BACKEND_URL}/assist/context`, { method: 'POST' });
  return r.json();
}

export async function getCurrentContext() {
  const r = await fetch(`${BACKEND_URL}/context/current`);
  return r.json();
}

export async function getTools(deviceAdapter?: string) {
  const qs = deviceAdapter ? `?device_adapter=${encodeURIComponent(deviceAdapter)}` : '';
  const r = await fetch(`${BACKEND_URL}/tools${qs}`);
  return r.json();
}

export async function getDevices() {
  const r = await fetch(`${BACKEND_URL}/devices`);
  return r.json();
}

export async function getMemoryItems() {
  const r = await fetch(`${BACKEND_URL}/memory/items`);
  return r.json();
}

export async function createMemoryItem(body: any) {
  const r = await fetch(`${BACKEND_URL}/memory/items`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
  });
  return r.json();
}

export async function updateMemoryItem(memoryId: string, patch: any) {
  const r = await fetch(`${BACKEND_URL}/memory/items/${encodeURIComponent(memoryId)}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(patch)
  });
  return r.json();
}

export async function deleteMemoryItem(memoryId: string, archive = true) {
  const r = await fetch(`${BACKEND_URL}/memory/items/${encodeURIComponent(memoryId)}?archive=${archive ? 'true' : 'false'}`, { method: 'DELETE' });
  return r.json();
}

export async function searchMemoryItems(query: string, taskType?: string, limit = 4) {
  const r = await fetch(`${BACKEND_URL}/memory/search`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ query, task_type: taskType, permission: 'private', limit })
  });
  return r.json();
}

export async function getWorkflows() {
  const r = await fetch(`${BACKEND_URL}/workflows`);
  return r.json();
}

export async function getWorkflowSuggestions() {
  const r = await fetch(`${BACKEND_URL}/workflows/suggestions`);
  return r.json();
}

export async function getProfileStatus() {
  const r = await fetch(`${BACKEND_URL}/profile/status`);
  return r.json();
}

export async function getBrand() {
  const r = await fetch(`${BACKEND_URL}/brand`);
  return r.json();
}

export async function updateBrand(patch: any) {
  const r = await fetch(`${BACKEND_URL}/brand`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(patch)
  });
  return r.json();
}

export async function getLicenseStatus() {
  const r = await fetch(`${BACKEND_URL}/license/status`);
  return r.json();
}

export async function activateLicense(token: string, accountEmail?: string) {
  const r = await fetch(`${BACKEND_URL}/license/activate`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ token, account_email: accountEmail || undefined })
  });
  return r.json();
}

export async function getIdentities() {
  const r = await fetch(`${BACKEND_URL}/identities`);
  return r.json();
}

export async function getActiveIdentity() {
  const r = await fetch(`${BACKEND_URL}/identities/active`);
  return r.json();
}

export async function getActiveIdentityAttestation() {
  const r = await fetch(`${BACKEND_URL}/identities/active/attestation`);
  return r.json();
}

export async function setActiveIdentity(identityId: string) {
  const r = await fetch(`${BACKEND_URL}/identities/active`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ identity_id: identityId })
  });
  return r.json();
}

export async function updateProfileStatus(patch: any) {
  const r = await fetch(`${BACKEND_URL}/profile/status`, {
    method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch)
  });
  return r.json();
}

export async function getGuardianStatus(runId?: string) {
  const qs = runId ? `?run_id=${encodeURIComponent(runId)}` : '';
  const r = await fetch(`${BACKEND_URL}/guardian/status${qs}`);
  return r.json();
}

export async function getCostSummary() {
  const r = await fetch(`${BACKEND_URL}/cost/summary`);
  return r.json();
}

export async function getCostModels() {
  const r = await fetch(`${BACKEND_URL}/cost/models`);
  return r.json();
}

export async function getLocalModelStatus() {
  const r = await fetch(`${BACKEND_URL}/local-model/status`);
  return r.json();
}

export async function selectModel(modelId: string) {
  const r = await fetch(`${BACKEND_URL}/models/select?model_id=${encodeURIComponent(modelId)}`, { method: 'POST' });
  return r.json();
}

export async function pullLocalModel(model: string, approved: boolean) {
  const r = await fetch(`${BACKEND_URL}/local-model/pull`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ model, approved, select_after_pull: true })
  });
  return r.json();
}

export async function startLocalModelRuntime() {
  const r = await fetch(`${BACKEND_URL}/local-model/start`, { method: 'POST' });
  return r.json();
}

export async function compactMemory(scope?: string) {
  const r = await fetch(`${BACKEND_URL}/memory/compact`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ scope, older_than_days: 30 })
  });
  return r.json();
}

export async function createWorkflow(body: any) {
  const r = await fetch(`${BACKEND_URL}/workflows`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body)
  });
  return r.json();
}

export async function runWorkflow(workflowId: string, context?: any) {
  const r = await fetch(`${BACKEND_URL}/workflows/${workflowId}/run`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ variables: {}, context })
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
