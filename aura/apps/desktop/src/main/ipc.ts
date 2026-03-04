import { ipcMain, shell, app } from 'electron';

export function registerIpcHandlers() {
  ipcMain.handle('aura:open-logs', async () => {
    const logsPath = app.getPath('logs');
    await shell.openPath(logsPath);
    return logsPath;
  });
}
