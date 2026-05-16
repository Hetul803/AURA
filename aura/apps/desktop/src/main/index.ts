import { app, BrowserWindow, Tray } from 'electron';
import fs from 'node:fs';
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
let overlayWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let isQuitting = false;

function overlayStatePath() {
  return path.join(app.getPath('userData'), 'overlay-state.json');
}

function readOverlayBounds() {
  try {
    const raw = fs.readFileSync(overlayStatePath(), 'utf8');
    const parsed = JSON.parse(raw);
    if (Number.isFinite(parsed.x) && Number.isFinite(parsed.y)) return { x: parsed.x, y: parsed.y };
  } catch {
    // Keep the default position when no saved overlay state exists.
  }
  return undefined;
}

function saveOverlayBounds(win: BrowserWindow) {
  try {
    const [x, y] = win.getPosition();
    fs.mkdirSync(path.dirname(overlayStatePath()), { recursive: true });
    fs.writeFileSync(overlayStatePath(), JSON.stringify({ x, y, updatedAt: new Date().toISOString() }, null, 2));
  } catch {
    // Position persistence should never crash AURA.
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 820,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs')
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
  win.webContents.on('render-process-gone', (_event, details) => {
    if (!devUrl) {
      win.loadURL(rendererFallbackUrl(`Renderer process failed: ${details.reason}\nExit code: ${details.exitCode}`));
    }
  });
  mainWindow = win;
  win.on('minimize', () => {
    showOverlay();
  });
  win.on('hide', () => {
    showOverlay();
  });
  return win;
}

function loadRenderer(win: BrowserWindow, overlay = false) {
  const devUrl = process.env.ELECTRON_DEV_URL;
  if (devUrl) {
    win.loadURL(overlay ? `${devUrl}${devUrl.includes('?') ? '&' : '?'}overlay=1` : devUrl);
  } else if (rendererExists(__dirname)) {
    win.loadFile(productionRendererPath(__dirname), overlay ? { query: { overlay: '1' } } : undefined);
  } else {
    win.loadURL(rendererFallbackUrl(`Missing renderer: ${productionRendererPath(__dirname)}`));
  }
}

function createOverlayWindow() {
  if (overlayWindow && !overlayWindow.isDestroyed()) return overlayWindow;
  const saved = readOverlayBounds();
  const win = new BrowserWindow({
    width: 340,
    height: 420,
    x: saved?.x,
    y: saved?.y,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      backgroundThrottling: false,
    }
  });
  win.setAlwaysOnTop(true, 'floating');
  if (process.platform === 'darwin') win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  loadRenderer(win, true);
  win.once('ready-to-show', () => {
    if (!mainWindow?.isVisible()) win.show();
  });
  win.on('moved', () => saveOverlayBounds(win));
  win.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      win.hide();
    }
  });
  overlayWindow = win;
  return win;
}

function showOverlay() {
  const win = createOverlayWindow();
  win.show();
  win.focus();
  return { ok: true, visible: true };
}

function hideOverlay() {
  overlayWindow?.hide();
  return { ok: true, visible: false };
}

function toggleOverlay() {
  const win = createOverlayWindow();
  if (win.isVisible()) {
    win.hide();
    return { ok: true, visible: false };
  }
  win.show();
  win.focus();
  return { ok: true, visible: true };
}

function openFullApp() {
  if (!mainWindow || mainWindow.isDestroyed()) mainWindow = createWindow();
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
  hideOverlay();
  mainWindow.webContents.send('aura:hotkey', { mode: 'compact_command', active: true, source: 'overlay' });
  return { ok: true };
}

app.whenReady().then(() => {
  registerIpcHandlers({ showOverlay, hideOverlay, toggleOverlay, openFullApp });
  const win = createWindow();
  createOverlayWindow();
  setHotkeyStatus(registerHotkeys(win));
  tray = createTray(win);
  waitForBackend(12).then((status) => {
    if (status !== 'Connected') console.warn(`AURA backend startup status: ${status}`);
  });
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    const win = createWindow();
    createOverlayWindow();
    setHotkeyStatus(registerHotkeys(win));
    tray = tray || createTray(win);
  } else {
    mainWindow?.show();
  }
});

app.on('will-quit', () => {
  isQuitting = true;
  unregisterHotkeys();
  stopManagedBackend();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
