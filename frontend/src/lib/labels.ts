const EFFORT_LABELS: Record<string, string> = {
  small: "Small",
  medium: "Medium",
  large: "Large",
  high: "Large",
};

export function effortLabel(effort: string | undefined): string {
  return EFFORT_LABELS[effort ?? ""] ?? effort ?? "Unknown effort";
}

const ACTION_LABELS: Record<string, string> = {
  start_task: "Begin this task",
  await_dependency: "Waiting on earlier work",
  no_action: "Nothing needs action right now",
};

export function actionLabel(action: string | undefined): string {
  return ACTION_LABELS[action ?? ""] ?? action ?? "No action available";
}

const PRIORITY_LABELS: Record<string, string> = {
  low: "Low priority",
  medium: "Medium priority",
  high: "High priority",
};

export function priorityLabel(priority: string | undefined): string {
  return PRIORITY_LABELS[priority ?? ""] ?? priority ?? "Medium priority";
}

const DEADLINE_LABELS: Record<string, string> = {
  none: "No deadline pressure",
  low: "Comfortable timeline",
  medium: "Deadline approaching",
  high: "Urgent deadline",
  overdue: "Past due",
};

export function deadlineLabel(pressure: string | undefined): string {
  return DEADLINE_LABELS[pressure ?? ""] ?? pressure ?? "No deadline pressure";
}

const TASK_STATUS_LABELS: Record<string, string> = {
  pending: "Not started",
  ready: "Ready to start",
  in_progress: "In progress",
  completed: "Complete",
  blocked: "Blocked",
  cancelled: "Cancelled",
};

export function taskStatusLabel(status: string | undefined): string {
  return TASK_STATUS_LABELS[status ?? ""] ?? status ?? "Not started";
}

const EXECUTION_STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Building",
  needs_review: "Needs review",
  completed: "Complete",
  failed: "Failed",
};

export function executionStatusLabel(status: string | undefined): string {
  return EXECUTION_STATUS_LABELS[status ?? ""] ?? status ?? "Unknown";
}

export function validationLabel(valid: boolean | undefined): string {
  if (valid === true) return "Ready to use";
  if (valid === false) return "Needs revision";
  return "Not checked";
}
