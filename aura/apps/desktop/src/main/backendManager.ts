import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from 'child_process';
import fs from 'fs';
import path from 'path';

const BACKEND_URL = process.env.AURA_BACKEND_URL || 'http://127.0.0.1:8000';
const HEALTH_URL = `${BACKEND_URL.replace(/\/$/, '')}/health`;
const DEFAULT_PYTHON_CANDIDATES = [process.env.AURA_BACKEND_PYTHON || '', 'python3', 'python'].filter(Boolean);
const STARTUP_TIMEOUT_MS = 15_000;
const MAX_LOG_CHARS = 6000;

export type BackendConnection = 'Connected' | 'Disconnected';
export type BackendLifecycle = 'idle' | 'starting' | 'connected' | 'error';

export type BackendState = {
  lifecycle: BackendLifecycle;
  connection: BackendConnection;
  url: string;
  managedByDesktop: boolean;
  usingExternalBackend: boolean;
  launchAttempted: boolean;
  message: string;
  detail: string;
  healthCheckedAt: number | null;
  pid: number | null;
  backendDir: string;
  pythonCommand: string;
  startupCommand: string[];
  startupLog: string;
};

let managedProcess: ChildProcessWithoutNullStreams | null = null;
let managedByDesktop = false;
let backendState: BackendState = {
  lifecycle: 'idle',
  connection: 'Disconnected',
  url: BACKEND_URL,
  managedByDesktop: false,
  usingExternalBackend: false,
  launchAttempted: false,
  message: 'Desktop backend lifecycle has not started yet.',
  detail: '',
  healthCheckedAt: null,
  pid: null,
  backendDir: '',
  pythonCommand: '',
  startupCommand: [],
  startupLog: '',
};
const listeners = new Set<(state: BackendState) => void>();

function emitState() {
  const snapshot = getBackendState();
  for (const listener of listeners) listener(snapshot);
}

function setBackendState(patch: Partial<BackendState>) {
  backendState = { ...backendState, ...patch };
  emitState();
}

function appendLog(chunk: string) {
  if (!chunk) return;
  const startupLog = `${backendState.startupLog}${chunk}`.slice(-MAX_LOG_CHARS);
  setBackendState({ startupLog, detail: startupLog.trim() });
}

function backendDir() {
  if (appBackendDirOverride()) return appBackendDirOverride();
  if (process.resourcesPath) {
    const packagedDir = path.join(process.resourcesPath, 'backend');
    if (fs.existsSync(packagedDir)) return packagedDir;
  }
  return path.resolve(__dirname, '../../../backend');
}

function appBackendDirOverride() {
  const override = process.env.AURA_BACKEND_DIR;
  return override ? path.resolve(override) : '';
}

function requirementsPath(backendRoot: string) {
  return path.join(backendRoot, 'requirements-private-alpha.txt');
}

function backendEntryPath(backendRoot: string) {
  return path.join(backendRoot, 'src', 'api', 'main.py');
}

function backendDependencyHelp(backendRoot: string, pythonCommand: string) {
  return [
    'AURA Mac private alpha requires a local Python runtime plus backend dependencies.',
    `Install them with: ${pythonCommand} -m pip install -r "${requirementsPath(backendRoot)}"`,
    'If you plan to test browser/research flows, also run: python3 -m playwright install chromium',
  ].join('\n');
}

function backendCommand(backendRoot: string, userDataPath: string, pythonCommand: string) {
  const env = {
    ...process.env,
    PYTHONPATH: [path.join(backendRoot, 'src'), process.env.PYTHONPATH || ''].filter(Boolean).join(path.delimiter),
    PROFILE_DIR_OVERRIDE: process.env.PROFILE_DIR_OVERRIDE || path.join(userDataPath, 'backend-profile'),
  };
  return {
    cwd: backendRoot,
    env,
    args: ['-m', 'uvicorn', 'src.api.main:app', '--host', '127.0.0.1', '--port', '8000'],
    pythonCommand,
  };
}

async function healthcheck(): Promise<BackendConnection> {
  try {
    const response = await fetch(HEALTH_URL);
    const connection = response.ok ? 'Connected' : 'Disconnected';
    setBackendState({ connection, healthCheckedAt: Date.now() });
    return connection;
  } catch {
    setBackendState({ connection: 'Disconnected', healthCheckedAt: Date.now() });
    return 'Disconnected';
  }
}

function pythonReady(command: string) {
  const result = spawnSync(command, ['-c', 'import fastapi, uvicorn, pydantic, httpx, playwright'], { encoding: 'utf-8' });
  return {
    ok: result.status === 0,
    detail: `${result.stdout || ''}${result.stderr || ''}`.trim(),
  };
}

function resolvePythonCommand() {
  for (const candidate of DEFAULT_PYTHON_CANDIDATES) {
    const check = pythonReady(candidate);
    if (check.ok) return { command: candidate, detail: '' };
  }
  const attempted = DEFAULT_PYTHON_CANDIDATES.join(', ');
  return {
    command: DEFAULT_PYTHON_CANDIDATES[0] || 'python3',
    detail: `Could not find a Python runtime with FastAPI/Uvicorn/Pydantic available. Tried: ${attempted || 'none'}.`,
  };
}

export function getBackendState(): BackendState {
  return { ...backendState, startupCommand: [...backendState.startupCommand] };
}

export function onBackendState(listener: (state: BackendState) => void) {
  listeners.add(listener);
  listener(getBackendState());
  return () => listeners.delete(listener);
}

export async function checkBackend(): Promise<BackendConnection> {
  return healthcheck();
}

export async function ensureBackend(userDataPath: string): Promise<BackendState> {
  const existing = await healthcheck();
  const root = backendDir();
  setBackendState({ backendDir: root, url: BACKEND_URL });
  if (existing === 'Connected') {
    setBackendState({
      lifecycle: 'connected',
      managedByDesktop: false,
      usingExternalBackend: true,
      launchAttempted: false,
      message: 'Connected to an already-running backend.',
      detail: '',
      pid: null,
      startupCommand: [],
      pythonCommand: '',
      startupLog: '',
    });
    return getBackendState();
  }
  if (managedProcess && !managedProcess.killed) {
    return getBackendState();
  }
  if (!fs.existsSync(root)) {
    setBackendState({
      lifecycle: 'error',
      managedByDesktop: false,
      usingExternalBackend: false,
      launchAttempted: true,
      message: 'AURA could not locate its bundled backend files.',
      detail: `Expected backend directory at ${root}. Rebuild the Mac private-alpha app so the backend resources are packaged into Contents/Resources/backend.`,
      pid: null,
      startupCommand: [],
      pythonCommand: '',
      startupLog: '',
    });
    return getBackendState();
  }
  if (!fs.existsSync(backendEntryPath(root))) {
    setBackendState({
      lifecycle: 'error',
      managedByDesktop: false,
      usingExternalBackend: false,
      launchAttempted: true,
      message: 'AURA found a backend bundle, but it is incomplete.',
      detail: `Expected backend entrypoint at ${backendEntryPath(root)}.`,
      pid: null,
      startupCommand: [],
      pythonCommand: '',
      startupLog: '',
    });
    return getBackendState();
  }

  const python = resolvePythonCommand();
  if (python.detail) {
    setBackendState({
      lifecycle: 'error',
      managedByDesktop: false,
      usingExternalBackend: false,
      launchAttempted: true,
      message: 'AURA could not start the backend because the local Python runtime is missing required packages.',
      detail: `${python.detail}\n${backendDependencyHelp(root, python.command)}`,
      pid: null,
      startupCommand: [],
      pythonCommand: python.command,
      startupLog: '',
    });
    return getBackendState();
  }

  const command = backendCommand(root, userDataPath, python.command);
  setBackendState({
    lifecycle: 'starting',
    connection: 'Disconnected',
    managedByDesktop: true,
    usingExternalBackend: false,
    launchAttempted: true,
    message: 'Starting the local AURA backend…',
    detail: '',
    pid: null,
    backendDir: root,
    pythonCommand: command.pythonCommand,
    startupCommand: [command.pythonCommand, ...command.args],
    startupLog: '',
  });

  managedProcess = spawn(command.pythonCommand, command.args, {
    cwd: command.cwd,
    env: command.env,
    stdio: 'pipe',
  });
  managedByDesktop = true;
  setBackendState({ pid: managedProcess.pid || null });
  managedProcess.stdout.on('data', (chunk) => appendLog(String(chunk)));
  managedProcess.stderr.on('data', (chunk) => appendLog(String(chunk)));
  managedProcess.on('exit', (code, signal) => {
    managedProcess = null;
    const detail = backendState.startupLog || `Backend exited before becoming healthy (code=${code}, signal=${signal}).`;
    setBackendState({
      lifecycle: backendState.connection === 'Connected' ? 'error' : 'error',
      connection: 'Disconnected',
      managedByDesktop: managedByDesktop,
      usingExternalBackend: false,
      message: 'AURA backend exited unexpectedly.',
      detail,
      pid: null,
    });
  });

  const startedAt = Date.now();
  while (Date.now() - startedAt < STARTUP_TIMEOUT_MS) {
    await new Promise((resolve) => setTimeout(resolve, 350));
    if ((await healthcheck()) === 'Connected') {
      setBackendState({
        lifecycle: 'connected',
        managedByDesktop: true,
        usingExternalBackend: false,
        message: 'Desktop-managed backend is healthy.',
        detail: backendState.startupLog.trim(),
        pid: managedProcess?.pid || null,
      });
      return getBackendState();
    }
    if (!managedProcess || managedProcess.killed) break;
  }

  setBackendState({
    lifecycle: 'error',
    managedByDesktop: true,
    usingExternalBackend: false,
    message: 'AURA could not make the backend healthy in time.',
    detail: backendState.startupLog || 'No backend startup logs were captured.',
    pid: managedProcess?.pid || null,
  });
  return getBackendState();
}

export async function waitForBackend(userDataPath: string, maxAttempts = 2): Promise<BackendState> {
  let attempt = 0;
  let state = getBackendState();
  while (attempt < maxAttempts) {
    state = await ensureBackend(userDataPath);
    if (state.connection === 'Connected') return state;
    attempt += 1;
  }
  return state;
}

export async function stopManagedBackend(): Promise<void> {
  if (!managedProcess || !managedByDesktop) return;
  managedProcess.kill('SIGTERM');
  await new Promise((resolve) => setTimeout(resolve, 400));
  if (managedProcess && !managedProcess.killed) managedProcess.kill('SIGKILL');
  managedProcess = null;
  setBackendState({
    lifecycle: 'idle',
    connection: 'Disconnected',
    managedByDesktop: false,
    usingExternalBackend: false,
    message: 'Desktop-managed backend stopped.',
    pid: null,
  });
}
