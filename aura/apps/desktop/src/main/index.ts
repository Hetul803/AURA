import { app, BrowserWindow, Tray } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';
import { stopManagedBackend, waitForBackend } from './backendManager.js';
import { registerIpcHandlers } from './ipc.js';
import { registerHotkeys, unregisterHotkeys } from './hotkeys.js';
import { createTray } from './tray.js';

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
  if (devUrl) win.loadURL(devUrl);
  else win.loadFile(path.join(__dirname, '../../dist/index.html'));
  mainWindow = win;
  return win;
}

app.whenReady().then(async () => {
  registerIpcHandlers();
  await waitForBackend(12);
  const win = createWindow();
  registerHotkeys(win);
  tray = createTray(win);
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    const win = createWindow();
    registerHotkeys(win);
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
