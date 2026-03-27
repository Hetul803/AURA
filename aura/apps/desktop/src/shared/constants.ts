export const DEFAULT_HOTKEY_MAC = 'Alt+Space';
export const DEFAULT_HOTKEY_OTHER = 'CommandOrControl+Shift+Space';
export const HOTKEY = (globalThis as any)?.process?.platform === 'darwin' ? DEFAULT_HOTKEY_MAC : DEFAULT_HOTKEY_OTHER;
export const BACKEND_URL = (globalThis as any)?.process?.env?.AURA_BACKEND_URL || 'http://localhost:8000';
