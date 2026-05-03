import { describe, expect, it, vi } from 'vitest';

vi.mock('electron', () => ({
  globalShortcut: {
    register: vi.fn(() => true),
    unregister: vi.fn(),
    unregisterAll: vi.fn(),
  },
}));

import { defaultHotkeyForPlatform, registerHotkey, replaceHotkey } from '../src/main/hotkeys';

describe('main hotkeys', () => {
  it('selects a sensible macOS default accelerator', () => {
    expect(defaultHotkeyForPlatform('darwin')).toBe('Alt+Space');
    expect(defaultHotkeyForPlatform('linux')).toBe('CommandOrControl+Shift+Space');
  });

  it('reports successful global hotkey registration', () => {
    const shortcut = {
      register: vi.fn(() => true),
      unregister: vi.fn(),
    };
    const result = registerHotkey(shortcut, 'Alt+Space', vi.fn());
    expect(result.ok).toBe(true);
    expect(shortcut.register).toHaveBeenCalledWith('Alt+Space', expect.any(Function));
  });

  it('surfaces failed global hotkey registration', () => {
    const shortcut = {
      register: vi.fn(() => false),
      unregister: vi.fn(),
    };
    const result = registerHotkey(shortcut, 'Alt+Space', vi.fn());
    expect(result.ok).toBe(false);
    expect(result.error).toMatch(/Failed to register global hotkey/);
  });

  it('replaces an existing hotkey before registering a new one', () => {
    const shortcut = {
      register: vi.fn(() => true),
      unregister: vi.fn(),
    };
    const result = replaceHotkey(shortcut, 'CommandOrControl+Shift+Space', 'Alt+Space', vi.fn());
    expect(result.ok).toBe(true);
    expect(shortcut.unregister).toHaveBeenCalledWith('CommandOrControl+Shift+Space');
    expect(shortcut.register).toHaveBeenCalledWith('Alt+Space', expect.any(Function));
  });
});
