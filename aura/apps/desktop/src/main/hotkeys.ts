import { HOTKEY } from '../shared/constants.js';
import { BrowserWindow, globalShortcut } from 'electron';

type ShortcutRegistry = {
  register(accelerator: string, callback: () => void): boolean;
  unregister(accelerator: string): void;
  unregisterAll?: () => void;
};

export function defaultHotkeyForPlatform(platform: string = process.platform) {
  return platform === 'darwin' ? 'Alt+Space' : 'CommandOrControl+Shift+Space';
}

export function registerHotkey(shortcut: ShortcutRegistry, accelerator: string, callback: () => void) {
  const ok = shortcut.register(accelerator, callback);
  return ok ? { ok: true, accelerator } : { ok: false, accelerator, error: `Failed to register global hotkey: ${accelerator}` };
}

export function replaceHotkey(shortcut: ShortcutRegistry, previous: string, next: string, callback: () => void) {
  shortcut.unregister(previous);
  return registerHotkey(shortcut, next, callback);
}

export function registerHotkeys(win: BrowserWindow) {
  return registerHotkey(globalShortcut, HOTKEY || defaultHotkeyForPlatform(), () => {
    if (win.isVisible() && win.isFocused()) {
      win.hide();
      return;
    }
    win.show();
    win.focus();
  }).ok;
}

export function unregisterHotkeys() {
  globalShortcut.unregisterAll();
}
