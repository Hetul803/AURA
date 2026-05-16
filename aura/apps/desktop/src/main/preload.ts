import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron';

contextBridge.exposeInMainWorld('auraDesktop', {
  openLogs: () => ipcRenderer.invoke('aura:open-logs'),
  getHotkeyStatus: () => ipcRenderer.invoke('aura:get-hotkey-status'),
  getDiagnostics: () => ipcRenderer.invoke('aura:get-diagnostics'),
  getSystemVoices: () => ipcRenderer.invoke('aura:get-system-voices'),
  repairBackend: () => ipcRenderer.invoke('aura:repair-backend'),
  reportRendererIssue: (issue: any) => ipcRenderer.invoke('aura:renderer-issue', issue),
  speakText: (text: string, options?: any) => ipcRenderer.invoke('aura:speak-text', text, options),
  nativeSpeechStatus: () => ipcRenderer.invoke('aura:native-speech-status'),
  nativeTranscribe: (options?: any) => ipcRenderer.invoke('aura:native-transcribe', options),
  showOverlay: () => ipcRenderer.invoke('aura:overlay-show'),
  hideOverlay: () => ipcRenderer.invoke('aura:overlay-hide'),
  toggleOverlay: () => ipcRenderer.invoke('aura:overlay-toggle'),
  openFullApp: () => ipcRenderer.invoke('aura:open-full-app'),
  onHotkey: (callback: (payload: any) => void) => {
    const listener = (_event: IpcRendererEvent, payload: any) => callback(payload);
    ipcRenderer.on('aura:hotkey', listener);
    return () => ipcRenderer.removeListener('aura:hotkey', listener);
  }
});
