import type {
  IngestResponse,
  WorkRequestInput,
  WorkflowState,
  WorkflowSummary,
  WorkflowEvent,
  WorkflowEvidence,
} from "./workflow-types";

// Local Vite development can run without a frontend/.env file. Keep the
// default aligned with backend/scripts/run_api.py while allowing deployments
// to provide their own API URL at build time.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export type BackendStatus = "checking" | "active" | "inactive" | "error";

export class ApiError extends Error {
  status: number;
  type: "network" | "http" | "cors" | "unknown";

  constructor(status: number, message: string, type: "network" | "http" | "cors" | "unknown" = "unknown") {
    super(message);
    this.status = status;
    this.type = type;
  }
}

export async function checkBackendHealth(): Promise<BackendStatus> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: "GET",
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (response.ok) {
      const data = await response.json();
      if (data.status === "ok") {
        return "active";
      }
      return "inactive";
    }
    return "inactive";
  } catch (err: unknown) {
    if (err instanceof TypeError && err.message.includes("fetch")) {
      return "error";
    }
    return "error";
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(0, `Cannot reach the backend at ${API_BASE_URL}. Is the API running?`, "network");
  }
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // fall through with the default message
    }
    const errorType: "http" | "cors" | "unknown" = response.status === 403 ? "cors" : "http";
    throw new ApiError(response.status, detail, errorType);
  }
  return (await response.json()) as T;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function createGoalRequest(
  input: WorkRequestInput,
  sync = false,
): Promise<WorkflowState> {
  return requestJson<WorkflowState>(`/goals?sync=${sync}`, jsonInit("POST", input));
}

export async function getWorkflowStatusRequest(
  workflowId: string,
): Promise<{ workflow_id: string; execution_state: string; execution_error: string | null; updated_at: string | null }> {
  return requestJson(`/goals/${encodeURIComponent(workflowId)}/status`);
}

export async function pollWorkflowUntilComplete(
  workflowId: string,
  onProgress?: (state: WorkflowState) => void,
  maxAttempts = 60,
  intervalMs = 1000,
): Promise<WorkflowState> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const statusData = await getWorkflowStatusRequest(workflowId);
    
    // Create a minimal workflow object for progress callback
    const progressState: WorkflowState = {
      workflow_id: workflowId,
      original_goal: "",
      execution_state: statusData.execution_state as WorkflowState["execution_state"],
      execution_error: statusData.execution_error,
      work_request: null,
      objective_analysis: null,
      goal_analysis: null,
      planner_steps: [],
      procedure_analysis: null,
      procedures: [],
      requirements: [],
      candidate_plan: null,
      plan_validation: null,
      plan_revision_count: 0,
      optimization: null,
      tasks: [],
      completed_tasks: [],
      blocked_tasks: [],
      current_task: null,
      current_state: {},
      retrieved_documents: [],
      detected_blockers: [],
      recommendation: null,
      memory_context: [],
      execution_metadata: {},
      version: 1,
      last_assessed_at: null,
    };
    
    if (onProgress) onProgress(progressState);
    
    if (statusData.execution_state === "completed" || statusData.execution_state === "failed") {
      // Fetch the full workflow data
      return getWorkflowRequest(workflowId);
    }
    
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  
  // Return the last known state if max attempts reached
  return getWorkflowRequest(workflowId);
}

export function continueGoalRequest(
  workflowId: string,
  completedTaskIds: string[],
): Promise<WorkflowState> {
  return requestJson<WorkflowState>(
    `/goals/${encodeURIComponent(workflowId)}/continue`,
    jsonInit("POST", { completed_task_ids: completedTaskIds }),
  );
}

export function getWorkflowRequest(workflowId: string): Promise<WorkflowState> {
  return requestJson<WorkflowState>(
    `/workflows/${encodeURIComponent(workflowId)}`,
  );
}

export function listWorkflowsRequest(): Promise<WorkflowSummary[]> {
  return requestJson<WorkflowSummary[]>("/workflows");
}

export async function ingestDocumentRequest(
  file: File,
  workflowId?: string,
): Promise<IngestResponse> {
  const body = new FormData();
  body.append("file", file);
  if (workflowId) body.append("workflow_id", workflowId);
  return requestJson<IngestResponse>("/documents/ingest", {
    method: "POST",
    body,
  });
}

export function refreshWorkflowRequest(workflowId: string): Promise<WorkflowState> {
  return requestJson<WorkflowState>(
    `/workflows/${encodeURIComponent(workflowId)}/refresh`,
    { method: "POST" },
  );
}

export function transitionTaskRequest(workflowId: string, taskId: string, status: string, version: number, reason?: string): Promise<WorkflowState> {
  return requestJson(`/workflows/${encodeURIComponent(workflowId)}/tasks/${encodeURIComponent(taskId)}/transition`, jsonInit("POST", { status, version, reason }));
}
export function submitUpdateRequest(workflowId: string, text: string, version: number): Promise<WorkflowState> {
  return requestJson(`/workflows/${encodeURIComponent(workflowId)}/updates`, jsonInit("POST", { text, version }));
}
export function listEventsRequest(workflowId: string): Promise<WorkflowEvent[]> { return requestJson(`/workflows/${encodeURIComponent(workflowId)}/events`); }
export function listEvidenceRequest(workflowId: string): Promise<WorkflowEvidence[]> { return requestJson(`/workflows/${encodeURIComponent(workflowId)}/evidence`); }
export function decideRecommendationRequest(workflowId: string, recommendationId: string, decision: string, version: number, reason?: string): Promise<WorkflowState> {
  return requestJson(`/workflows/${encodeURIComponent(workflowId)}/recommendations/${encodeURIComponent(recommendationId)}/decision`, jsonInit("POST", { decision, version, reason }));
}
