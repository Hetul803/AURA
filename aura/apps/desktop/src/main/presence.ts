import fs from 'fs';
import path from 'path';
import { HOTKEY } from '../shared/constants.js';

export type PresenceSettings = {
  hotkey: string;
  overlayEnabled: boolean;
};

export type PresenceState = PresenceSettings & {
  hotkeyRegistered: boolean;
  hotkeyError: string;
  overlayVisible: boolean;
  activeRunId: string;
  pendingApprovalRunId: string;
  lastRunStatus: string;
  overlayInvokedAt?: number;
  overlayVisibleAt?: number;
};

const DEFAULT_SETTINGS: PresenceSettings = {
  hotkey: HOTKEY,
  overlayEnabled: true,
};

let settingsPath = '';
let currentState: PresenceState = {
  ...DEFAULT_SETTINGS,
  hotkeyRegistered: false,
  hotkeyError: '',
  overlayVisible: false,
  activeRunId: '',
  pendingApprovalRunId: '',
  lastRunStatus: 'idle',
};

function persistable(state: PresenceState) {
  return {
    hotkey: state.hotkey,
    overlayEnabled: state.overlayEnabled,
    activeRunId: state.activeRunId,
    pendingApprovalRunId: state.pendingApprovalRunId,
    lastRunStatus: state.lastRunStatus,
    overlayInvokedAt: state.overlayInvokedAt,
    overlayVisibleAt: state.overlayVisibleAt,
  };
}

function loadSettings(): Partial<PresenceState> {
  if (!settingsPath || !fs.existsSync(settingsPath)) return { ...DEFAULT_SETTINGS };
  try {
    const parsed = JSON.parse(fs.readFileSync(settingsPath, 'utf8')) as Partial<PresenceState>;
    return {
      hotkey: parsed.hotkey || DEFAULT_SETTINGS.hotkey,
      overlayEnabled: parsed.overlayEnabled ?? DEFAULT_SETTINGS.overlayEnabled,
      activeRunId: parsed.activeRunId || '',
      pendingApprovalRunId: parsed.pendingApprovalRunId || '',
      lastRunStatus: parsed.lastRunStatus || 'idle',
      overlayInvokedAt: parsed.overlayInvokedAt,
      overlayVisibleAt: parsed.overlayVisibleAt,
    };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

function saveSettings(state: PresenceState) {
  if (!settingsPath) return;
  fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
  fs.writeFileSync(settingsPath, JSON.stringify(persistable(state), null, 2));
}

export function initPresence(userDataPath: string): PresenceState {
  settingsPath = path.join(userDataPath, 'presence-settings.json');
  currentState = { ...currentState, ...loadSettings(), overlayVisible: false };
  saveSettings(currentState);
  return currentState;
}

export function getPresenceState(): PresenceState {
  return { ...currentState };
}

export function updatePresenceState(patch: Partial<PresenceState>, persist = false): PresenceState {
  currentState = { ...currentState, ...patch };
  if (persist || patch.activeRunId !== undefined || patch.pendingApprovalRunId !== undefined || patch.lastRunStatus !== undefined) saveSettings(currentState);
  return getPresenceState();
}
