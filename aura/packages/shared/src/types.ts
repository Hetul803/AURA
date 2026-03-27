export type SafetyLevel = 'SAFE' | 'CONFIRM' | 'BLOCKED';

export type StepActionType =
  | 'OS_OPEN_APP' | 'OS_OPEN_URL' | 'WEB_NAVIGATE' | 'WEB_CLICK' | 'WEB_TYPE'
  | 'WEB_READ' | 'SCREENSHOT' | 'CLIPBOARD_COPY' | 'CLIPBOARD_PASTE' | 'WAIT_FOR' | 'NOOP';
