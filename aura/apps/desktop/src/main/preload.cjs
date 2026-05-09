const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('auraDesktop', {
  openLogs: () => ipcRenderer.invoke('aura:open-logs'),
  getHotkeyStatus: () => ipcRenderer.invoke('aura:get-hotkey-status'),
  getDiagnostics: () => ipcRenderer.invoke('aura:get-diagnostics'),
  repairBackend: () => ipcRenderer.invoke('aura:repair-backend'),
  reportRendererIssue: (issue) => ipcRenderer.invoke('aura:renderer-issue', issue),
  speakText: (text) => ipcRenderer.invoke('aura:speak-text', text),
  showOverlay: () => ipcRenderer.invoke('aura:overlay-show'),
  hideOverlay: () => ipcRenderer.invoke('aura:overlay-hide'),
  toggleOverlay: () => ipcRenderer.invoke('aura:overlay-toggle'),
  openFullApp: () => ipcRenderer.invoke('aura:open-full-app'),
  onHotkey: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on('aura:hotkey', listener);
    return () => ipcRenderer.removeListener('aura:hotkey', listener);
  },
});
