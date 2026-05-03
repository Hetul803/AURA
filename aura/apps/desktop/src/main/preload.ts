import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron';

contextBridge.exposeInMainWorld('auraDesktop', {
  openLogs: () => ipcRenderer.invoke('aura:open-logs'),
  getHotkeyStatus: () => ipcRenderer.invoke('aura:get-hotkey-status'),
  onHotkey: (callback: (payload: any) => void) => {
    const listener = (_event: IpcRendererEvent, payload: any) => callback(payload);
    ipcRenderer.on('aura:hotkey', listener);
    return () => ipcRenderer.removeListener('aura:hotkey', listener);
  }
});
