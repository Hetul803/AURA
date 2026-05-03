import { app, BrowserWindow, Tray } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';
import { stopManagedBackend, waitForBackend } from './backendManager.js';
import { registerIpcHandlers, setHotkeyStatus } from './ipc.js';
import { registerHotkeys, unregisterHotkeys } from './hotkeys.js';
import { createTray } from './tray.js';
import { productionRendererPath, rendererExists, rendererFallbackUrl } from './rendererPaths.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;

function createWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 820,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js')
    }
  });

  const devUrl = process.env.ELECTRON_DEV_URL;
  if (devUrl) {
    win.loadURL(devUrl);
  } else if (rendererExists(__dirname)) {
    win.loadFile(productionRendererPath(__dirname));
  } else {
    win.loadURL(rendererFallbackUrl(`Missing renderer: ${productionRendererPath(__dirname)}`));
  }
  win.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedUrl) => {
    if (!devUrl) {
      win.loadURL(rendererFallbackUrl(`Renderer load failed: ${errorCode} ${errorDescription}\n${validatedUrl}`));
    }
  });
  mainWindow = win;
  return win;
}

app.whenReady().then(() => {
  registerIpcHandlers();
  const win = createWindow();
  setHotkeyStatus(registerHotkeys(win));
  tray = createTray(win);
  waitForBackend(12).then((status) => {
    if (status !== 'Connected') console.warn(`AURA backend startup status: ${status}`);
  });
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    const win = createWindow();
    setHotkeyStatus(registerHotkeys(win));
    tray = tray || createTray(win);
  } else {
    mainWindow?.show();
  }
});

app.on('will-quit', () => {
  unregisterHotkeys();
  stopManagedBackend();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
