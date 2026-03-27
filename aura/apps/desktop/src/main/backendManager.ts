const BACKEND = process.env.AURA_BACKEND_URL || 'http://localhost:8000';

export type BackendStatus = 'Connected' | 'Disconnected';

export async function checkBackend(): Promise<BackendStatus> {
  try {
    const r = await fetch(`${BACKEND}/health`);
    return r.ok ? 'Connected' : 'Disconnected';
  } catch {
    return 'Disconnected';
  }
}

export async function waitForBackend(maxAttempts = 8): Promise<BackendStatus> {
  let attempt = 0;
  let delay = 250;
  while (attempt < maxAttempts) {
    const status = await checkBackend();
    if (status === 'Connected') return status;
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * 2, 3000);
    attempt += 1;
  }
  return 'Disconnected';
}
