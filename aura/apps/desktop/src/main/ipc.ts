import { ipcMain, shell, app } from 'electron';
import os from 'node:os';
import path from 'node:path';
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

export function setHotkeyStatus(status: HotkeyStatus) {
  hotkeyStatus = status;
}

export function registerIpcHandlers() {
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
}
