import { ipcMain, shell, app } from 'electron';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { backendDiagnostics, ensureBackendStarted, repairBackendDependencies } from './backendManager.js';

type HotkeyStatus = {
  ok: boolean;
  accelerator: string;
  error?: string;
};

let hotkeyStatus: HotkeyStatus = {
  ok: false,
  accelerator: 'CommandOrControl+Shift+Space',
  error: 'Hotkey has not registered yet.',
};

type WindowControls = {
  showOverlay?: () => Promise<any> | any;
  hideOverlay?: () => Promise<any> | any;
  toggleOverlay?: () => Promise<any> | any;
  openFullApp?: () => Promise<any> | any;
};

let windowControls: WindowControls = {};

export function setHotkeyStatus(status: HotkeyStatus) {
  hotkeyStatus = status;
}

function speakWithSystemVoice(text: string, options: { voice?: string; rate?: number } = {}) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim().slice(0, 600);
  if (!clean) return { ok: false, status: 'empty_text', message: 'Nothing to speak.' };
  if (process.platform !== 'darwin') {
    return { ok: false, status: 'unsupported_platform', message: 'System voice fallback is only implemented for macOS right now.' };
  }
  const args: string[] = [];
  if (options.voice) args.push('-v', String(options.voice).slice(0, 64));
  if (options.rate && Number.isFinite(options.rate)) args.push('-r', String(Math.max(120, Math.min(260, Math.round(options.rate)))));
  args.push(clean);
  const child = spawn('say', args, { detached: true, stdio: 'ignore' });
  child.unref();
  return { ok: true, status: 'speaking', provider: 'macos_say' };
}

function listSystemVoices(): Promise<{ ok: boolean; voices: string[]; provider?: string; message?: string }> {
  if (process.platform !== 'darwin') {
    return Promise.resolve({ ok: false, voices: [], message: 'System voice listing is only available on macOS.' });
  }
  return new Promise((resolve) => {
    const child = spawn('say', ['-v', '?'], { stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '';
    child.stdout.on('data', (chunk) => { out += chunk.toString(); });
    child.on('close', () => {
      const voices = out.split('\n')
        .map((line) => line.trim().split(/\s+/)[0])
        .filter(Boolean)
        .filter((voice, index, arr) => arr.indexOf(voice) === index)
        .slice(0, 80);
      resolve({ ok: voices.length > 0, voices, provider: 'macos_say' });
    });
    child.on('error', (error) => resolve({ ok: false, voices: [], message: error.message }));
  });
}

export function registerIpcHandlers(controls: WindowControls = {}) {
  windowControls = controls;
  ipcMain.handle('aura:open-logs', async () => {
    const logsPath = app.getPath('logs');
    await shell.openPath(logsPath);
    return logsPath;
  });
  ipcMain.handle('aura:get-hotkey-status', async () => hotkeyStatus);
  ipcMain.handle('aura:get-diagnostics', async () => ({
    appVersion: app.getVersion(),
    appPath: app.getAppPath(),
    executablePath: app.getPath('exe'),
    installedAppPath: process.platform === 'darwin' ? '/Applications/AURA.app' : app.getPath('exe'),
    resourcesPath: process.resourcesPath,
    userDataPath: app.getPath('userData'),
    logsPath: app.getPath('logs'),
    profilePath: process.env.AURA_PROFILE_DIR || path.join(os.homedir(), '.aura'),
    packaged: app.isPackaged,
    platform: process.platform,
    backend: backendDiagnostics(),
  }));
  ipcMain.handle('aura:repair-backend', async () => {
    const result = await repairBackendDependencies();
    if (result.ok) await ensureBackendStarted();
    return result;
  });
  ipcMain.handle('aura:renderer-issue', async (_event, issue) => {
    const logsPath = app.getPath('logs');
    fs.mkdirSync(logsPath, { recursive: true });
    const line = JSON.stringify({ at: new Date().toISOString(), source: 'renderer', issue }) + '\n';
    fs.appendFileSync(path.join(logsPath, 'aura-renderer.log'), line);
    return { ok: true };
  });
  ipcMain.handle('aura:get-system-voices', async () => listSystemVoices());
  ipcMain.handle('aura:speak-text', async (_event, text: string, options?: { voice?: string; rate?: number }) => speakWithSystemVoice(text, options || {}));
  ipcMain.handle('aura:overlay-show', async () => windowControls.showOverlay?.() ?? { ok: false, message: 'Overlay controls are not ready.' });
  ipcMain.handle('aura:overlay-hide', async () => windowControls.hideOverlay?.() ?? { ok: false, message: 'Overlay controls are not ready.' });
  ipcMain.handle('aura:overlay-toggle', async () => windowControls.toggleOverlay?.() ?? { ok: false, message: 'Overlay controls are not ready.' });
  ipcMain.handle('aura:open-full-app', async () => windowControls.openFullApp?.() ?? { ok: false, message: 'Main window controls are not ready.' });
}
