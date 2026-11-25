import { describe, expect, it } from "vitest";

import {
  actionLabel,
  deadlineLabel,
  effortLabel,
  executionStatusLabel,
  priorityLabel,
  taskStatusLabel,
  validationLabel,
} from "./labels";

describe("UI labels", () => {
  it("uses friendly effort and action text", () => {
    expect(effortLabel("high")).toBe("Large");
    expect(actionLabel("start_task")).toBe("Begin this task");
    expect(actionLabel(undefined)).toBe("No action available");
  });

  it("uses friendly priority and deadline text", () => {
    expect(priorityLabel("high")).toBe("High priority");
    expect(deadlineLabel("overdue")).toBe("Past due");
    expect(deadlineLabel("unknown")).toBe("unknown");
  });

  it("uses friendly task and execution text", () => {
    expect(taskStatusLabel("in_progress")).toBe("In progress");
    expect(executionStatusLabel("needs_review")).toBe("Needs review");
    expect(executionStatusLabel("never_seen")).toBe("never_seen");
  });

  it("summarizes plan validation without technical flags", () => {
    expect(validationLabel(true)).toBe("Ready to use");
    expect(validationLabel(false)).toBe("Needs revision");
    expect(validationLabel(undefined)).toBe("Not checked");
  });
});
