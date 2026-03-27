import { app, BrowserWindow, globalShortcut } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';
import { getBackendState, onBackendState, stopManagedBackend, waitForBackend } from './backendManager.js';
import { registerHotkey, replaceHotkey } from './hotkeys.js';
import { completeOnboarding, getOnboardingState, initOnboarding, updateOnboardingState } from './onboarding.js';
import { getPresenceState, initPresence, updatePresenceState } from './presence.js';
import { registerIpcHandlers } from './ipc.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let dashboardWindow: BrowserWindow | null = null;
let overlayWindow: BrowserWindow | null = null;
let quitting = false;

function rendererUrl(surface: 'dashboard' | 'overlay') {
  const devUrl = process.env.ELECTRON_DEV_URL;
  if (devUrl) return `${devUrl}?surface=${surface}`;
  return path.join(__dirname, '../renderer/index.html');
}

function loadSurface(win: BrowserWindow, surface: 'dashboard' | 'overlay') {
  const devUrl = process.env.ELECTRON_DEV_URL;
  if (devUrl) return win.loadURL(rendererUrl(surface));
  return win.loadFile(rendererUrl(surface), { query: { surface } });
}

function broadcastPresence() {
  const state = getPresenceState();
  for (const win of [dashboardWindow, overlayWindow]) {
    if (win && !win.isDestroyed()) win.webContents.send('aura:presence-state', state);
  }
}

function broadcastBackend() {
  const state = getBackendState();
  for (const win of [dashboardWindow, overlayWindow]) {
    if (win && !win.isDestroyed()) win.webContents.send('aura:backend-state', state);
  }
}

function showDashboard() {
  if (!dashboardWindow || dashboardWindow.isDestroyed()) createDashboardWindow();
  dashboardWindow?.show();
  dashboardWindow?.focus();
}

function showOverlay() {
  if (!overlayWindow || overlayWindow.isDestroyed()) createOverlayWindow();
  updatePresenceState({ overlayVisible: true, overlayInvokedAt: Date.now() }, true);
  overlayWindow?.show();
  overlayWindow?.focus();
  broadcastPresence();
}

function hideOverlay() {
  if (overlayWindow && !overlayWindow.isDestroyed()) overlayWindow.hide();
  updatePresenceState({ overlayVisible: false }, true);
  broadcastPresence();
}

function createDashboardWindow() {
  dashboardWindow = new BrowserWindow({
    width: 1200,
    height: 820,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js')
    }
  });
  dashboardWindow.on('closed', () => { dashboardWindow = null; });
  void loadSurface(dashboardWindow, 'dashboard');
}

function createOverlayWindow() {
  overlayWindow = new BrowserWindow({
    width: 560,
    height: 540,
    resizable: false,
    maximizable: false,
    minimizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    autoHideMenuBar: true,
    titleBarStyle: 'hiddenInset',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js')
    }
  });
  overlayWindow.on('close', (event) => {
    if (!quitting) {
      event.preventDefault();
      hideOverlay();
    }
  });
  overlayWindow.on('hide', () => {
    updatePresenceState({ overlayVisible: false }, true);
    broadcastPresence();
  });
  overlayWindow.on('show', () => {
    updatePresenceState({ overlayVisible: true, overlayVisibleAt: Date.now() }, true);
    broadcastPresence();
  });
  overlayWindow.on('closed', () => { overlayWindow = null; });
  void loadSurface(overlayWindow, 'overlay');
}

function registerGlobalHotkey() {
  const state = getPresenceState();
  globalShortcut.unregister(state.hotkey);
  if (!state.overlayEnabled) {
    updatePresenceState({ hotkeyRegistered: false, hotkeyError: '' }, true);
    broadcastPresence();
    return;
  }
  const result = registerHotkey(globalShortcut, state.hotkey, () => showOverlay());
  updatePresenceState({ hotkeyRegistered: result.ok, hotkeyError: result.error || '' }, true);
  broadcastPresence();
}

app.whenReady().then(async () => {
  initPresence(app.getPath('userData'));
  initOnboarding(app.getPath('userData'));
  registerIpcHandlers({
    getPresenceState,
    updatePresenceState: (patch) => {
      const next = updatePresenceState(patch, true);
      broadcastPresence();
      return next;
    },
    updatePresenceSettings: (patch) => {
      const previous = getPresenceState().hotkey;
      const next = updatePresenceState({
        hotkey: typeof patch.hotkey === 'string' && patch.hotkey ? patch.hotkey : getPresenceState().hotkey,
        overlayEnabled: typeof patch.overlayEnabled === 'boolean' ? patch.overlayEnabled : getPresenceState().overlayEnabled,
      }, true);
      if (previous !== next.hotkey || patch.overlayEnabled !== undefined) {
        if (!next.overlayEnabled) {
          globalShortcut.unregister(previous);
          updatePresenceState({ hotkeyRegistered: false, hotkeyError: '' }, true);
        } else {
          const result = replaceHotkey(globalShortcut, previous, next.hotkey, () => showOverlay());
          updatePresenceState({ hotkeyRegistered: result.ok, hotkeyError: result.error || '' }, true);
        }
      }
      broadcastPresence();
      return getPresenceState();
    },
    getOnboardingState,
    updateOnboardingState: (patch) => updateOnboardingState(patch),
    completeOnboarding,
    getBackendState,
    showOverlay,
    hideOverlay,
    showDashboard,
  });
  onBackendState(() => broadcastBackend());
  createDashboardWindow();
  createOverlayWindow();
  registerGlobalHotkey();
  broadcastPresence();
  broadcastBackend();
  await waitForBackend(app.getPath('userData'));
  broadcastBackend();
});

app.on('activate', () => {
  if (!dashboardWindow) showDashboard();
});

app.on('before-quit', async () => {
  quitting = true;
  globalShortcut.unregisterAll();
  await stopManagedBackend();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
