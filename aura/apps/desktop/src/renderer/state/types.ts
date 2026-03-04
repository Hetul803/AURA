export type TimelineEvent = {
  run_id: string;
  step_id?: string;
  name?: string;
  safety_level?: string;
  status: string;
  timestamp?: number;
  message?: string;
  type?: string;
};
