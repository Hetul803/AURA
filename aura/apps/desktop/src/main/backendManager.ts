import { app } from 'electron';
import { spawn, type ChildProcessWithoutNullStreams } from 'child_process';
import fs from 'fs';
import path from 'path';
import { findBackendDir } from './backendPaths.js';

const BACKEND = process.env.AURA_BACKEND_URL || 'http://localhost:8000';
const DEFAULT_PORT = process.env.AURA_BACKEND_PORT || '8000';

export type BackendStatus = 'Connected' | 'Disconnected' | 'Starting';

let backendProcess: ChildProcessWithoutNullStreams | null = null;
let logStream: fs.WriteStream | null = null;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function pythonExecutable(): string {
  return process.env.AURA_BACKEND_PYTHON || process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
}

function venvPython() {
  const venvDir = path.join(app.getPath('userData'), 'backend-venv');
  return process.platform === 'win32'
    ? path.join(venvDir, 'Scripts', 'python.exe')
    : path.join(venvDir, 'bin', 'python3');
}

function pythonForBackend() {
  const repairedPython = venvPython();
  if (!process.env.AURA_BACKEND_PYTHON && fs.existsSync(repairedPython)) {
    return repairedPython;
  }
  return pythonExecutable();
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
    command: pythonForBackend(),
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

  const backendDir = findBackendDir({
    cwd: process.cwd(),
    appPath: app.getAppPath(),
    resourcesPath: process.resourcesPath,
    envBackendDir: process.env.AURA_BACKEND_DIR,
  });
  if (!backendDir) {
    appendLog(`[backend] unable to locate backend from cwd=${process.cwd()} appPath=${app.getAppPath()} resources=${process.resourcesPath}\n`);
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

function runRepairStep(command: string, args: string[], cwd: string) {
  appendLog(`[backend-repair] ${command} ${args.join(' ')} cwd=${cwd}\n`);
  return new Promise<{ ok: boolean; code: number | null }>((resolve) => {
    const child = spawn(command, args, {
      cwd,
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
      shell: process.platform === 'win32',
    });
    child.stdout.on('data', (chunk) => appendLog(chunk.toString()));
    child.stderr.on('data', (chunk) => appendLog(chunk.toString()));
    child.on('exit', (code) => resolve({ ok: code === 0, code }));
    child.on('error', (error) => {
      appendLog(`[backend-repair] failed to start ${command}: ${error.message}\n`);
      resolve({ ok: false, code: null });
    });
  });
}

export async function repairBackendDependencies() {
  const backendDir = findBackendDir({
    cwd: process.cwd(),
    appPath: app.getAppPath(),
    resourcesPath: process.resourcesPath,
    envBackendDir: process.env.AURA_BACKEND_DIR,
  });
  if (!backendDir) {
    appendLog('[backend-repair] backend directory not found\n');
    return { ok: false, message: 'Backend directory was not found in app resources or repo checkout.' };
  }
  const requirements = path.join(backendDir, 'requirements-private-alpha.txt');
  if (!fs.existsSync(requirements)) {
    appendLog(`[backend-repair] missing requirements: ${requirements}\n`);
    return { ok: false, message: `Backend requirements file is missing: ${requirements}` };
  }

  const venvDir = path.dirname(path.dirname(venvPython()));
  fs.mkdirSync(app.getPath('userData'), { recursive: true });
  if (!fs.existsSync(venvPython())) {
    const created = await runRepairStep(pythonExecutable(), ['-m', 'venv', venvDir], backendDir);
    if (!created.ok) return { ok: false, message: 'Could not create backend Python environment. Open logs for details.' };
  }

  const pipUpgrade = await runRepairStep(venvPython(), ['-m', 'pip', 'install', '--upgrade', 'pip'], backendDir);
  if (!pipUpgrade.ok) return { ok: false, message: 'Could not upgrade pip in backend environment. Open logs for details.' };
  const installed = await runRepairStep(venvPython(), ['-m', 'pip', 'install', '-r', requirements], backendDir);
  if (!installed.ok) return { ok: false, message: 'Could not install backend dependencies. Open logs for details.' };
  appendLog(`[backend-repair] ready: ${venvPython()}\n`);
  return { ok: true, message: 'Backend dependencies repaired. Restarting AURA Core.', python: venvPython(), backendDir };
}

export function backendDiagnostics() {
  const backendDir = findBackendDir({
    cwd: process.cwd(),
    appPath: app.getAppPath(),
    resourcesPath: process.resourcesPath,
    envBackendDir: process.env.AURA_BACKEND_DIR,
  });
  const cmd = backendDir ? backendCommand(backendDir) : null;
  return {
    backendUrl: BACKEND,
    backendDir,
    logPath: path.join(app.getPath('logs'), 'aura-backend.log'),
    command: cmd ? `${cmd.command} ${cmd.args.join(' ')}` : '',
    usingRepairedVenv: fs.existsSync(venvPython()),
    repairedPython: venvPython(),
  };
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
