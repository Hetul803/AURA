import { app, ipcMain, shell } from 'electron';
import type { BackendState } from './backendManager.js';
import type { OnboardingState } from './onboarding.js';
import type { PresenceState } from './presence.js';

export type IpcHandlers = {
  getPresenceState: () => PresenceState;
  updatePresenceState: (patch: Partial<PresenceState>) => PresenceState;
  updatePresenceSettings: (patch: Partial<PresenceState>) => PresenceState;
  getOnboardingState: () => OnboardingState;
  updateOnboardingState: (patch: Partial<OnboardingState>) => OnboardingState;
  completeOnboarding: () => OnboardingState;
  getBackendState: () => BackendState;
  showOverlay: () => void;
  hideOverlay: () => void;
  showDashboard: () => void;
};

export function registerIpcHandlers(handlers: IpcHandlers) {
  ipcMain.handle('aura:open-logs', async () => {
    const logsPath = app.getPath('logs');
    await shell.openPath(logsPath);
    return logsPath;
  });
  ipcMain.handle('aura:presence:get', async () => handlers.getPresenceState());
  ipcMain.handle('aura:presence:update', async (_event, patch: Partial<PresenceState>) => handlers.updatePresenceState(patch || {}));
  ipcMain.handle('aura:settings:update', async (_event, patch: Partial<PresenceState>) => handlers.updatePresenceSettings(patch || {}));
  ipcMain.handle('aura:onboarding:get', async () => handlers.getOnboardingState());
  ipcMain.handle('aura:onboarding:update', async (_event, patch: Partial<OnboardingState>) => handlers.updateOnboardingState(patch || {}));
  ipcMain.handle('aura:onboarding:complete', async () => handlers.completeOnboarding());
  ipcMain.handle('aura:backend:get', async () => handlers.getBackendState());
  ipcMain.handle('aura:overlay:show', async () => {
    handlers.showOverlay();
    return handlers.getPresenceState();
  });
  ipcMain.handle('aura:overlay:hide', async () => {
    handlers.hideOverlay();
    return handlers.getPresenceState();
  });
  ipcMain.handle('aura:dashboard:show', async () => {
    handlers.showDashboard();
    return handlers.getPresenceState();
  });
}
