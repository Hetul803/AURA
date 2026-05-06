const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('auraDesktop', {
  openLogs: () => ipcRenderer.invoke('aura:open-logs'),
  getHotkeyStatus: () => ipcRenderer.invoke('aura:get-hotkey-status'),
  getDiagnostics: () => ipcRenderer.invoke('aura:get-diagnostics'),
  repairBackend: () => ipcRenderer.invoke('aura:repair-backend'),
  reportRendererIssue: (issue) => ipcRenderer.invoke('aura:renderer-issue', issue),
  onHotkey: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on('aura:hotkey', listener);
    return () => ipcRenderer.removeListener('aura:hotkey', listener);
  },
});
