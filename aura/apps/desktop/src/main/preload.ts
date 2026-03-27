import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('auraDesktop', {
  openLogs: () => ipcRenderer.invoke('aura:open-logs'),
  getPresenceState: () => ipcRenderer.invoke('aura:presence:get'),
  updatePresenceState: (patch: Record<string, unknown>) => ipcRenderer.invoke('aura:presence:update', patch),
  updateSettings: (patch: Record<string, unknown>) => ipcRenderer.invoke('aura:settings:update', patch),
  getOnboardingState: () => ipcRenderer.invoke('aura:onboarding:get'),
  updateOnboardingState: (patch: Record<string, unknown>) => ipcRenderer.invoke('aura:onboarding:update', patch),
  completeOnboarding: () => ipcRenderer.invoke('aura:onboarding:complete'),
  getBackendState: () => ipcRenderer.invoke('aura:backend:get'),
  showOverlay: () => ipcRenderer.invoke('aura:overlay:show'),
  hideOverlay: () => ipcRenderer.invoke('aura:overlay:hide'),
  showDashboard: () => ipcRenderer.invoke('aura:dashboard:show'),
  onPresenceState: (callback: (state: unknown) => void) => {
    const listener = (_event: unknown, state: unknown) => callback(state);
    ipcRenderer.on('aura:presence-state', listener);
    return () => ipcRenderer.removeListener('aura:presence-state', listener);
  },
  onBackendState: (callback: (state: unknown) => void) => {
    const listener = (_event: unknown, state: unknown) => callback(state);
    ipcRenderer.on('aura:backend-state', listener);
    return () => ipcRenderer.removeListener('aura:backend-state', listener);
  },
});
