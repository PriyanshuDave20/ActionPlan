import { useCallback, useEffect, useRef, useState } from "react";

import {
  getWorkflowRequest,
  getWorkflowStatusRequest,
} from "../api/client";
import type { WorkflowState } from "../api/workflow-types";

export type ExecutionState =
  | "queued"
  | "running"
  | "needs_review"
  | "completed"
  | "failed";

const TERMINAL_STATES: ExecutionState[] = ["completed", "failed", "needs_review"];
const POLL_INTERVAL_MS = 3000;
const MAX_CONSECUTIVE_ERRORS = 5;

function isTerminal(state: string | null): boolean {
  return state !== null && TERMINAL_STATES.includes(state as ExecutionState);
}

/**
 * Reusable workflow lifecycle polling.
 *
 * - Polls the lightweight status endpoint every ~3s while the workflow is
 *   QUEUED or RUNNING; never overlaps requests.
 * - Stops polling at a terminal state and fetches the full workflow once.
 * - Tolerates transient network errors (keeps polling); only surfaces an
 *   error after MAX_CONSECUTIVE_ERRORS consecutive failures.
 * - Cleans up all timers when the component unmounts or the id changes.
 * - `refresh()` re-fetches the persisted workflow after explicit user
 *   actions (task continuation, decisions, document reassessment).
 */
export function useWorkflowStatus(workflowId: string) {
  const [executionState, setExecutionState] = useState<ExecutionState | null>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cancelledRef = useRef(false);
  const inFlightRef = useRef(false);
  const consecutiveErrorsRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchFullWorkflow = useCallback(async () => {
    const data = await getWorkflowRequest(workflowId);
    if (cancelledRef.current) return;
    setWorkflow(data);
    setExecutionState(data.execution_state);
    setExecutionError(data.execution_error ?? null);
  }, [workflowId]);

  useEffect(() => {
    cancelledRef.current = false;
    inFlightRef.current = false;
    consecutiveErrorsRef.current = 0;
    setExecutionState(null);
    setExecutionError(null);
    setWorkflow(null);
    setError(null);

    const poll = async () => {
      if (cancelledRef.current || inFlightRef.current) return;
      inFlightRef.current = true;
      try {
        const statusData = await getWorkflowStatusRequest(workflowId);
        if (cancelledRef.current) return;
        consecutiveErrorsRef.current = 0;
        setError(null);
        setExecutionState(statusData.execution_state as ExecutionState);
        setExecutionError(statusData.execution_error);

        if (isTerminal(statusData.execution_state)) {
          try {
            await fetchFullWorkflow();
          } catch (reason) {
            if (!cancelledRef.current) {
              setError(reason instanceof Error ? reason.message : String(reason));
            }
          }
          inFlightRef.current = false;
          return; // terminal: stop polling
        }
      } catch (reason) {
        if (cancelledRef.current) return;
        consecutiveErrorsRef.current += 1;
        if (consecutiveErrorsRef.current >= MAX_CONSECUTIVE_ERRORS) {
          setError(reason instanceof Error ? reason.message : String(reason));
          inFlightRef.current = false;
          return; // give up after repeated failures
        }
        // transient error: keep polling
      }
      inFlightRef.current = false;
      if (!cancelledRef.current) {
        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      }
    };

    poll();

    return () => {
      cancelledRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [workflowId, fetchFullWorkflow]);

  const refresh = useCallback(async () => {
    await fetchFullWorkflow();
  }, [fetchFullWorkflow]);

  return {
    executionState,
    executionError,
    workflow,
    error,
    refresh,
    setWorkflow,
    isTerminal,
  };
}
