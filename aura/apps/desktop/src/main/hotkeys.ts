import { DEFAULT_HOTKEY_MAC, DEFAULT_HOTKEY_OTHER } from '../shared/constants.js';

export type GlobalShortcutLike = {
  register: (accelerator: string, callback: () => void) => boolean;
  unregister: (accelerator: string) => void;
};

export type HotkeyRegistrationResult = {
  ok: boolean;
  accelerator: string;
  error?: string;
};

export function defaultHotkeyForPlatform(platform = process.platform): string {
  return platform === 'darwin' ? DEFAULT_HOTKEY_MAC : DEFAULT_HOTKEY_OTHER;
}

export function registerHotkey(shortcut: GlobalShortcutLike, accelerator: string, onTrigger: () => void): HotkeyRegistrationResult {
  try {
    const ok = shortcut.register(accelerator, onTrigger);
    if (!ok) return { ok: false, accelerator, error: `Failed to register global hotkey: ${accelerator}` };
    return { ok: true, accelerator };
  } catch (error) {
    return {
      ok: false,
      accelerator,
      error: error instanceof Error ? error.message : `Failed to register global hotkey: ${accelerator}`,
    };
  }
}

export function replaceHotkey(shortcut: GlobalShortcutLike, previousAccelerator: string | null | undefined, nextAccelerator: string, onTrigger: () => void): HotkeyRegistrationResult {
  if (previousAccelerator) shortcut.unregister(previousAccelerator);
  return registerHotkey(shortcut, nextAccelerator, onTrigger);
}
