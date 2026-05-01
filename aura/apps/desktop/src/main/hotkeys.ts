import { HOTKEY } from '../shared/constants.js';
import { BrowserWindow, globalShortcut } from 'electron';

export function registerHotkeys(win: BrowserWindow) {
  return globalShortcut.register(HOTKEY, () => {
    if (win.isVisible() && win.isFocused()) {
      win.hide();
      return;
    }
    win.show();
    win.focus();
  });
}

export function unregisterHotkeys() {
  globalShortcut.unregisterAll();
}
