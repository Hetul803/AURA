import { app, BrowserWindow } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';
import { waitForBackend } from './backendManager.js';
import { registerIpcHandlers } from './ipc.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

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
  else win.loadFile(path.join(__dirname, '../renderer/index.html'));
}

app.whenReady().then(async () => {
  registerIpcHandlers();
  await waitForBackend();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
