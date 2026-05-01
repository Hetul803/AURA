import { app } from 'electron';
import { spawn, type ChildProcessWithoutNullStreams } from 'child_process';
import fs from 'fs';
import path from 'path';

const BACKEND = process.env.AURA_BACKEND_URL || 'http://localhost:8000';
const DEFAULT_PORT = process.env.AURA_BACKEND_PORT || '8000';

export type BackendStatus = 'Connected' | 'Disconnected' | 'Starting';

let backendProcess: ChildProcessWithoutNullStreams | null = null;
let logStream: fs.WriteStream | null = null;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function findBackendDir(start: string): string | null {
  let current = start;
  for (let i = 0; i < 8; i += 1) {
    const candidate = path.join(current, 'aura', 'apps', 'backend');
    if (fs.existsSync(path.join(candidate, 'src', 'api', 'main.py'))) return candidate;
    const nestedCandidate = path.join(current, 'apps', 'backend');
    if (fs.existsSync(path.join(nestedCandidate, 'src', 'api', 'main.py'))) return nestedCandidate;
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return null;
}

function pythonExecutable(): string {
  return process.env.AURA_BACKEND_PYTHON || process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
}

function backendCommand(backendDir: string) {
  if (process.env.AURA_BACKEND_COMMAND) {
    return {
      command: process.env.AURA_BACKEND_COMMAND,
      args: (process.env.AURA_BACKEND_ARGS || '').split(' ').filter(Boolean),
      cwd: backendDir,
    };
  }
  return {
    command: pythonExecutable(),
    args: ['-m', 'uvicorn', 'api.main:app', '--app-dir', 'src', '--host', '127.0.0.1', '--port', DEFAULT_PORT],
    cwd: backendDir,
  };
}

function appendLog(line: string) {
  if (!logStream) {
    fs.mkdirSync(app.getPath('logs'), { recursive: true });
    logStream = fs.createWriteStream(path.join(app.getPath('logs'), 'aura-backend.log'), { flags: 'a' });
  }
  logStream.write(line);
}

export async function checkBackend(): Promise<BackendStatus> {
  try {
    const r = await fetch(`${BACKEND}/health`);
    return r.ok ? 'Connected' : 'Disconnected';
  } catch {
    return 'Disconnected';
  }
}

export function stopManagedBackend() {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
  }
  backendProcess = null;
  logStream?.end();
  logStream = null;
}

export async function ensureBackendStarted(): Promise<BackendStatus> {
  const existing = await checkBackend();
  if (existing === 'Connected') return existing;
  if (process.env.AURA_BACKEND_URL) return existing;
  if (backendProcess) return 'Starting';

  const backendDir = findBackendDir(process.cwd()) || findBackendDir(app.getAppPath());
  if (!backendDir) {
    appendLog(`[backend] unable to locate backend from ${process.cwd()} or ${app.getAppPath()}\n`);
    return 'Disconnected';
  }

  const cmd = backendCommand(backendDir);
  appendLog(`[backend] starting: ${cmd.command} ${cmd.args.join(' ')} cwd=${cmd.cwd}\n`);
  backendProcess = spawn(cmd.command, cmd.args, {
    cwd: cmd.cwd,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    shell: process.platform === 'win32',
  });
  backendProcess.stdout.on('data', (chunk) => appendLog(chunk.toString()));
  backendProcess.stderr.on('data', (chunk) => appendLog(chunk.toString()));
  backendProcess.on('exit', (code, signal) => {
    appendLog(`[backend] exited code=${code} signal=${signal}\n`);
    backendProcess = null;
  });
  return 'Starting';
}

export async function waitForBackend(maxAttempts = 8): Promise<BackendStatus> {
  await ensureBackendStarted();
  let attempt = 0;
  let delay = 250;
  while (attempt < maxAttempts) {
    const status = await checkBackend();
    if (status === 'Connected') return status;
    await sleep(delay);
    delay = Math.min(delay * 2, 3000);
    attempt += 1;
  }
  return 'Disconnected';
}
