import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('auraDesktop', {
  openLogs: () => ipcRenderer.invoke('aura:open-logs')
});
