export type TimelineEvent = {
  run_id: string;
  step_id?: string;
  name?: string;
  safety_level?: string;
  status: string;
  timestamp?: number;
  message?: string;
  type?: string;
  url?: string;
  session?: string;
};

export type PresenceState = {
  hotkey: string;
  overlayEnabled: boolean;
  hotkeyRegistered: boolean;
  hotkeyError: string;
  overlayVisible: boolean;
  activeRunId: string;
  pendingApprovalRunId: string;
  lastRunStatus: string;
  overlayInvokedAt?: number;
  overlayVisibleAt?: number;
};

export type BackendState = {
  lifecycle: 'idle' | 'starting' | 'connected' | 'error';
  connection: 'Connected' | 'Disconnected';
  url: string;
  managedByDesktop: boolean;
  usingExternalBackend: boolean;
  launchAttempted: boolean;
  message: string;
  detail: string;
  healthCheckedAt: number | null;
  pid: number | null;
  backendDir: string;
  pythonCommand: string;
  startupCommand: string[];
  startupLog: string;
};

export type ModelStatus = {
  selected_model_id: string;
  selected_model: { provider: string; model: string; available: boolean };
  assist_model: Record<string, any>;
  available_models: Array<Record<string, any>>;
  ollama: {
    host: string;
    reachable: boolean;
    error: string | null;
    detail: string | null;
    models: string[];
  };
  using_local_model: boolean;
  selected_model_present: boolean;
  runtime_ready: boolean;
  assist_drafting_ready: boolean;
  readiness_code: string;
  summary: string;
  limitations: string[];
  setup_steps: string[];
  alpha_notes?: string[];
  demo_mode?: boolean;
};

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

export type GuardianEvent = {
  run_id: string;
  step_id?: string;
  action?: string;
  type: string;
  source: string;
  risk: 'low' | 'medium' | 'high';
  summary: string;
  explanation: string;
  context?: Record<string, any>;
  timestamp?: number;
};

export type HeroPhase = 'idle' | 'running' | 'capturing' | 'drafting' | 'awaiting_approval' | 'pasting' | 'completed' | 'needs_attention';

export type HeroTiming = {
  marks?: Record<string, number | null>;
  durations_ms?: Record<string, number | null>;
  phase?: HeroPhase;
  phase_label?: string;
  detail?: string;
  transitions?: Array<{ phase: HeroPhase | string; label: string; detail: string; timestamp: number }>;
  updated_at?: number;
};

export type DemoScenario = {
  id: string;
  label: string;
  description: string;
  command: string;
  task_kind: string;
};

export type DemoStatus = {
  enabled: boolean;
  scenarios: DemoScenario[];
};
