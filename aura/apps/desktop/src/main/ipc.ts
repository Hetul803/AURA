import { ipcMain, shell, app } from 'electron';

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
}
