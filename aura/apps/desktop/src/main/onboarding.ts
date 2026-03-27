import fs from 'fs';
import path from 'path';

export type OnboardingStepId =
  | 'welcome'
  | 'presence'
  | 'permissions'
  | 'model'
  | 'preferences'
  | 'first_task'
  | 'complete';

export type OnboardingState = {
  completed: boolean;
  currentStep: OnboardingStepId;
  startedAt: string | null;
  completedAt: string | null;
  dismissedAt: string | null;
  starterPreferencesSeeded: boolean;
  firstTaskCompleted: boolean;
  firstTaskRunId: string;
  usageMode: 'assist' | 'guided';
  approvalMode: 'strict' | 'balanced';
  proactiveEnabled: boolean;
  lastKnownReadiness: {
    hotkeyReady: boolean;
    modelReady: boolean;
    permissionsChecked: boolean;
  };
};

const DEFAULT_STATE: OnboardingState = {
  completed: false,
  currentStep: 'welcome',
  startedAt: null,
  completedAt: null,
  dismissedAt: null,
  starterPreferencesSeeded: false,
  firstTaskCompleted: false,
  firstTaskRunId: '',
  usageMode: 'assist',
  approvalMode: 'balanced',
  proactiveEnabled: true,
  lastKnownReadiness: {
    hotkeyReady: false,
    modelReady: false,
    permissionsChecked: false,
  },
};

let onboardingPath = '';
let currentState: OnboardingState = { ...DEFAULT_STATE };

function loadState(): OnboardingState {
  if (!onboardingPath || !fs.existsSync(onboardingPath)) return { ...DEFAULT_STATE };
  try {
    const parsed = JSON.parse(fs.readFileSync(onboardingPath, 'utf8')) as Partial<OnboardingState>;
    return {
      ...DEFAULT_STATE,
      ...parsed,
      lastKnownReadiness: {
        ...DEFAULT_STATE.lastKnownReadiness,
        ...(parsed.lastKnownReadiness || {}),
      },
    };
  } catch {
    return { ...DEFAULT_STATE };
  }
}

function saveState() {
  if (!onboardingPath) return;
  fs.mkdirSync(path.dirname(onboardingPath), { recursive: true });
  fs.writeFileSync(onboardingPath, JSON.stringify(currentState, null, 2));
}

export function initOnboarding(userDataPath: string): OnboardingState {
  onboardingPath = path.join(userDataPath, 'onboarding-state.json');
  currentState = loadState();
  if (!currentState.startedAt) currentState.startedAt = new Date().toISOString();
  saveState();
  return getOnboardingState();
}

export function getOnboardingState(): OnboardingState {
  return {
    ...currentState,
    lastKnownReadiness: { ...currentState.lastKnownReadiness },
  };
}

export function updateOnboardingState(patch: Partial<OnboardingState>): OnboardingState {
  currentState = {
    ...currentState,
    ...patch,
    lastKnownReadiness: {
      ...currentState.lastKnownReadiness,
      ...(patch.lastKnownReadiness || {}),
    },
  };
  if (!currentState.startedAt) currentState.startedAt = new Date().toISOString();
  saveState();
  return getOnboardingState();
}

export function completeOnboarding(): OnboardingState {
  currentState = {
    ...currentState,
    completed: true,
    currentStep: 'complete',
    completedAt: new Date().toISOString(),
    dismissedAt: null,
  };
  saveState();
  return getOnboardingState();
}
