import { useEffect, useRef, useState } from "react";

import {
  continueGoalRequest,
  createGoalRequest,
  listWorkflowsRequest,
  checkBackendHealth,
  ingestDocumentRequest,
  refreshWorkflowRequest,
  decideRecommendationRequest,
  executeRecommendationRequest,
  type BackendStatus,
} from "./api/client";
import type { WorkflowSummary } from "./api/workflow-types";
import { matchRoute, navigate, useHashRoute } from "./lib/useHashRoute";
import { setPendingUploads, takePendingUploads } from "./lib/pendingUploads";
import { useWorkflowStatus } from "./lib/useWorkflowPolling";

function Layout({
  children,
  activeWorkflows,
  backendStatus,
}: {
  children: React.ReactNode;
  activeWorkflows?: boolean;
  backendStatus?: BackendStatus;
}) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#/">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
          <span>Workplace Operations Agent</span>
        </a>

        <nav className="nav">
          <button type="button" onClick={() => navigate("")}>
            New project
          </button>

          <button type="button" onClick={() => navigate("history")}>
            Projects
          </button>

          <button type="button" onClick={() => navigate("about")}>
            About
          </button>

          {activeWorkflows ? (
            <span className="nav-badge">project open</span>
          ) : null}

          {backendStatus !== undefined ? (
            <span
              className={`nav-badge ${
                backendStatus === "active" ? "status-ok" : "status-error"
              }`}
            >
              Backend: {backendStatus}
            </span>
          ) : null}
        </nav>
      </header>

      <main className="content">{children}</main>

      <footer className="footer">
        Advisory agent - suggested actions are reviewed by people before being
        executed.
      </footer>
    </div>
  );
}

function Loading() {
  return <div className="card">Loading…</div>;
}

function ErrorBanner({ message }: { message: string }) {
  return <div className="card error-card">Error: {message}</div>;
}

const EFFORT_LABELS: Record<string, string> = {
  small: "Small",
  medium: "Medium",
  large: "Large",
  high: "Large",
};

function effortLabel(effort: string | undefined): string {
  if (!effort) return "—";
  return EFFORT_LABELS[effort] ?? effort;
}

const ACTION_LABELS: Record<string, string> = {
  start_task: "Begin this task",
  await_dependency: "Waiting on earlier work",
  no_action: "Nothing needs action right now",
};

function actionLabel(action: string | undefined): string {
  if (!action) return "—";
  return ACTION_LABELS[action] ?? action;
}

const PRIORITY_LABELS: Record<string, string> = {
  low: "Low priority",
  medium: "Medium priority",
  high: "High priority",
};

function priorityLabel(priority: string | undefined): string {
  return PRIORITY_LABELS[priority ?? ""] ?? priority ?? "Medium priority";
}

const DEADLINE_LABELS: Record<string, string> = {
  none: "No deadline pressure",
  low: "Comfortable timeline",
  medium: "Deadline approaching",
  high: "Urgent deadline",
  overdue: "Past due",
};

function deadlineLabel(pressure: string | undefined): string {
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

function taskStatusLabel(status: string | undefined): string {
  return TASK_STATUS_LABELS[status ?? ""] ?? status ?? "Not started";
}

const EXECUTION_STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Building",
  needs_review: "Needs review",
  completed: "Complete",
  failed: "Failed",
};

function executionStatusLabel(status: string | undefined): string {
  return EXECUTION_STATUS_LABELS[status ?? ""] ?? status ?? "Unknown";
}

function validationLabel(valid: boolean | undefined): string {
  if (valid === true) return "Ready to use";
  if (valid === false) return "Needs revision";
  return "Not checked";
}

function friendlyStateStatus(status: string): string {
  if (!status) return "—";
  if (/execution in progress/i.test(status)) {
    const match = status.match(/task (\d+) of (\d+)/i);
    if (match) {
      return `Your project plan is underway — step ${match[1]} of ${match[2]} is next.`;
    }
    return "Your project plan is being prepared.";
  }
  if (/all planned tasks are complete/i.test(status)) {
    return "All planned work is complete.";
  }
  if (/no plan produced/i.test(status)) {
    return "No plan has been produced yet.";
  }
  return status;
}

function friendlyError(reason: unknown): string {
  const message = reason instanceof Error ? reason.message : String(reason);
  if (/recommendation not found/i.test(message)) {
    return (
      "This suggestion has changed since the page was loaded. " +
      "Reload the project to see the current recommendation, then try again."
    );
  }
  return message;
}

function HomePage() {
  const [title, setTitle] = useState("Untitled project");
  const [goal, setGoal] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    if (!goal.trim()) {
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      setProgress("Creating project…");
      // Async creation: the backend persists a QUEUED workflow, enqueues the
      // job, and returns immediately. No waiting for the LangGraph run.
      const workflow = await createGoalRequest(
        { title: title.trim() || "Untitled project", goal: goal.trim() },
        false,
      );
      const workflowId = workflow.workflow_id;

      // Hand the selected files to the workflow page, which ingests them
      // while the plan builds in the background.
      setPendingUploads(files);

      // Navigate immediately; the workflow page shows live build status.
      window.location.hash = `#/workflow/${workflowId}`;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSubmitting(false);
      setProgress("");
    }
  }

  return (
    <section className="page">
      <p className="eyebrow">WORKPLACE OPERATIONS</p>
      <h1>Turn a project goal into a clear plan.</h1>

      <p className="lede">
        Start with the outcome you want. ActionPlan will analyze the objective,
        extract requirements, plan and validate an execution order, and
        recommend the next action - without executing anything automatically.
      </p>

      <form className="card form" onSubmit={handleSubmit}>
        <label className="field">
          <span>Project title</span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="e.g. Project Alpha launch plan"
            maxLength={160}
            disabled={submitting}
          />
        </label>

        <label className="field">
          <span>What are you working on?</span>

          <textarea
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder="e.g. Prepare Project Alpha for production by coordinating launch readiness, approvals, and team handoffs."
            rows={4}
            disabled={submitting}
            required
          />
        </label>

        <div className="initial-documents">
          <div>
            <span className="field-title">Project documents <span className="optional-label">Optional</span></span>
            <p className="muted">Add policies, briefs, or reference files now. They'll be indexed for your project while the plan builds.</p>
          </div>
          <label className={`button secondary initial-upload ${submitting ? "disabled" : ""}`}>
            <span aria-hidden="true">＋</span> Choose files
            <input
              type="file"
              accept=".pdf,.txt,.md,.csv"
              multiple
              disabled={submitting}
              onChange={(event) => {
                const additions = Array.from(event.currentTarget.files ?? []);
                setFiles((current) => [...current, ...additions.filter((file) => !current.some((existing) => existing.name === file.name))]);
                event.currentTarget.value = "";
              }}
            />
          </label>
          {files.length > 0 ? (
            <ul className="selected-files">
              {files.map((file) => (
                <li key={file.name}>
                  <span className="file-mark">DOC</span>
                  <span className="file-name">{file.name}</span>
                  {!submitting ? <button type="button" aria-label={`Remove ${file.name}`} onClick={() => setFiles((current) => current.filter((item) => item.name !== file.name))}>×</button> : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        {error ? <ErrorBanner message={error} /> : null}

        <button type="submit" className="primary" disabled={submitting}>
          {submitting ? (progress || "Creating project…") : "Create project →"}
        </button>
      </form>
    </section>
  );
}

type DocUploadStatus = { name: string; state: "indexing" | "added" | "error"; message?: string };

function WorkflowPage({ workflowId }: { workflowId: string }) {
  const {
    executionState,
    executionError,
    workflow,
    error: pollError,
    refresh,
    setWorkflow: setWorkflowState,
  } = useWorkflowStatus(workflowId);

  const [actionError, setActionError] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [docStatuses, setDocStatuses] = useState<DocUploadStatus[]>([]);
  const [reassessing, setReassessing] = useState(false);
  const [executingIntegration, setExecutingIntegration] = useState(false);
  const [jiraProject, setJiraProject] = useState("");
  const pendingRef = useRef<File[] | null>(null);
  const ingestionStartedRef = useRef(false);

  const documents = workflow?.execution_metadata?.documents ?? [];
  const projectTitle = workflow?.project_title?.trim() || workflow?.original_goal;

  // After the workflow reaches a terminal state, ingest any documents that
  // were selected during creation. Documents upload only once the initial
  // execution is finished, so there is no race with the background worker;
  // a single controlled reassessment follows successful ingestion.
  useEffect(() => {
    if (!workflow || ingestionStartedRef.current) return;
    if (pendingRef.current === null) {
      pendingRef.current = takePendingUploads();
    }
    const files = pendingRef.current;
    if (!files || files.length === 0) return;
    if (executionState !== "completed" && executionState !== "failed" && executionState !== "needs_review") return;

    ingestionStartedRef.current = true;

    (async () => {
      let anyAdded = false;
      let failure: string | null = null;
      for (const file of files) {
        setDocStatuses((current) => [
          ...current.filter((d) => d.name !== file.name),
          { name: file.name, state: "indexing" },
        ]);
        try {
          await ingestDocumentRequest(file, workflowId);
          anyAdded = true;
          setDocStatuses((current) => [
            ...current.filter((d) => d.name !== file.name),
            { name: file.name, state: "added" },
          ]);
        } catch (reason) {
          failure = `${file.name}: ${reason instanceof Error ? reason.message : String(reason)}`;
          setDocStatuses((current) => [
            ...current.filter((d) => d.name !== file.name),
            { name: file.name, state: "error", message: failure ?? undefined },
          ]);
          break; // keep the project accessible; surface the document error
        }
      }

      if (anyAdded && !failure && executionState === "completed") {
        // Explicit, controlled reassessment so the plan can incorporate the
        // newly indexed documents. Never runs for failed workflows.
        setReassessing(true);
        try {
          await refreshWorkflowRequest(workflowId);
          await refresh();
        } catch (reason) {
          setActionError(reason instanceof Error ? reason.message : String(reason));
        } finally {
          setReassessing(false);
        }
      }
    })();
  }, [workflow, executionState, workflowId, refresh]);

  async function handleContinue() {
    if (!workflow) {
      return;
    }
    setCompleting(true);
    setActionError(null);

    try {
      const next = await continueGoalRequest(
        workflow.workflow_id,
        workflow.completed_tasks ?? [],
      );
      setWorkflowState(next);
      setCompleting(false);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
      setCompleting(false);
    }
  }

  async function handleRetryAssessment() {
    setRetrying(true);
    setActionError(null);
    try {
      await refreshWorkflowRequest(workflowId);
      await refresh();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRetrying(false);
    }
  }

async function decide(decision: string) {
    if (!workflow?.recommendation?.recommendation_id) return;
    try { setWorkflowState(await decideRecommendationRequest(workflow.workflow_id, workflow.recommendation.recommendation_id, decision, workflow.version)); }
    catch (reason) { setActionError(friendlyError(reason)); }
  }

  async function handleExecuteIntegration(notifySlack: boolean, createJiraIssue: boolean) {
    const currentWorkflow = workflow;
    const recommendation = currentWorkflow?.recommendation;
    if (!currentWorkflow || !recommendation?.recommendation_id) return;
    setExecutingIntegration(true);
    setActionError(null);
    try {
      setWorkflowState(
        await executeRecommendationRequest(currentWorkflow.workflow_id, recommendation.recommendation_id, {
          version: currentWorkflow.version,
          notify_slack: notifySlack,
          create_jira_issue: createJiraIssue,
          jira_project: createJiraIssue ? jiraProject.trim() || undefined : undefined,
        }),
      );
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setExecutingIntegration(false);
    }
  }

  const error = pollError ?? actionError;

  if (error && !workflow) {
    return (
      <section className="page">
      <p className="eyebrow">PROJECT UNAVAILABLE</p>
      <h1>We couldn't open this project.</h1>
      <ErrorBanner message={error} />
      <button type="button" className="primary" onClick={() => navigate("history")}>Back to projects</button>
      </section>
    );
  }

  if (!workflow) {
    const statusText =
      executionState === "queued" ? "Queued…"
      : executionState === "running" ? "Building your project plan…"
      : executionState === "needs_review" ? "Awaiting review…"
      : "Loading…";
    return (
      <section className="page">
      <div className="card">
        <div className="meta-row">
          <div className="status status-checking">
            <span className="status-dot"></span>
            <span>{statusText}</span>
          </div>
        </div>
      </div>
      <p className="muted">The agent is preparing your plan — this usually takes under a minute. You can leave this page and come back; your project is saved.</p>
      {docStatuses.length > 0 ? (
        <ul className="selected-files">
          {docStatuses.map((doc) => (
            <li key={doc.name}>
              <span className="file-mark">DOC</span>
              <span className="file-name">{doc.name}</span>
              <span className={`doc-status doc-${doc.state}`}>
                {doc.state === "indexing" ? "Indexing…" : doc.state === "added" ? "Added" : "Failed"}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      </section>
    );
  }

  if (executionState === "failed" || executionError) {
    return (
      <section className="page">
      <p className="eyebrow">PROJECT ISSUE</p>
      <h1>{projectTitle}</h1>
      <span className="muted mono">{workflow.workflow_id}</span>
      <div className="card error-card" style={{ marginTop: 16 }}>
        <h3>The agent could not finish this assessment.</h3>
        <p>{executionError || "An unknown error occurred while building the plan."}</p>
        <p className="muted">Your project is saved. You can retry the assessment — nothing was executed automatically.</p>
        <div className="action-row">
          <button type="button" className="primary" onClick={handleRetryAssessment} disabled={retrying}>
            {retrying ? "Retrying…" : "Retry assessment"}
          </button>
          <button type="button" className="button secondary" onClick={handleContinue} disabled={completing || retrying}>
            {completing ? "Updating…" : "Continue workflow"}
          </button>
          <button type="button" className="button secondary" onClick={() => navigate("history")}>Back to projects</button>
        </div>
      </div>
      </section>
    );
  }

  const tasks = workflow.tasks ?? [];

  return (
    <section className="page">
    <div className="workflow-head">
    <div>
    <h1>{projectTitle}</h1>
    <span className="muted mono">{workflow.workflow_id}</span>
    </div>

      <button
        type="button"
        className="primary"
        onClick={handleContinue}
        disabled={completing}
      >
        {completing
          ? "Updating…"
          : "Continue workflow"}
      </button>
    </div>

    <div className="card documents-card">
      <div className="section-title-row">
        <div><p className="eyebrow">PROJECT KNOWLEDGE</p><h2>Documents</h2></div>
      </div>
      <p className="muted">Reference files indexed for this project. Ingested content is used as evidence for assessments.</p>
      {docStatuses.some((d) => d.state !== "added") || reassessing ? (
        <ul className="selected-files">
          {docStatuses.map((doc) => (
            <li key={doc.name}>
              <span className="file-mark">DOC</span>
              <span className="file-name">{doc.name}</span>
              <span className={`doc-status doc-${doc.state}`}>
                {doc.state === "indexing" ? "Indexing…" : doc.state === "added" ? "Added" : "Failed"}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {documents.length ? <ul className="document-list">{documents.map((name) => <li key={name}><span className="document-icon">↳</span>{name}</li>)}</ul> : <p className="empty-inline">No documents added yet.</p>}
      {reassessing ? <p className="muted">Updating the plan with your documents…</p> : null}
    </div>
    {error ? <ErrorBanner message={error} /> : null}

    {workflow.recommendation ? (
      <div className="card recommendation-card">
        <h2>
          Recommended next step: {actionLabel(workflow.recommendation.action)}
        </h2>

        <p>{workflow.recommendation.reason}</p>

        <div className="meta-row">
          <span>
            Task:{" "}
            {(() => {
              const recommendation = workflow.recommendation;
              if (!recommendation) return "—";
              const affected = (workflow.tasks ?? []).find(
                (t: any) => t.id === recommendation.affected_task,
              );
              return (
                <strong>
                  {affected ? affected.title || affected.description : "—"}
                </strong>
              );
            })()}
          </span>

            <span>{priorityLabel(workflow.recommendation.priority)}</span>

          <span>
            {deadlineLabel(workflow.recommendation.deadline_pressure)}
          </span>
        </div>
        <div className="action-row">
          {workflow.recommendation.recommendation_id && workflow.recommendation.status === "open" ? (
            <>
              <button className="primary" type="button" onClick={() => decide("accepted")}>Accept</button>
              <button className="button secondary" type="button" onClick={() => decide("rejected")}>Reject</button>
              <button className="button secondary" type="button" onClick={() => decide("revision_requested")}>Request revision</button>
            </>
          ) : null}

          {workflow.recommendation.recommendation_id && workflow.recommendation.status === "accepted" ? (
            <>
              <button
                type="button"
                className="button secondary"
                disabled={executingIntegration}
                onClick={() => handleExecuteIntegration(true, false)}
              >
                {executingIntegration ? "Sending…" : "Send to Slack"}
              </button>
              <label className="field">
                <span className="muted">Jira project</span>
                <input
                  value={jiraProject}
                  onChange={(event) => setJiraProject(event.target.value)}
                  placeholder="ENG"
                  disabled={executingIntegration}
                />
              </label>
              <button
                type="button"
                className="primary"
                disabled={executingIntegration || !jiraProject.trim()}
                onClick={() => handleExecuteIntegration(false, true)}
              >
                {executingIntegration ? "Creating…" : "Create Jira issue"}
              </button>
            </>
          ) : null}
        </div>
        <p className="muted">
          Slack and Jira are optional hand-offs. You can continue without either.
        </p>
      </div>
    ) : null}

    {workflow.current_state ? (
      <div className="card">
        <h3>Current state</h3>

        <div className="meta-row">
          <span>
            Status: {friendlyStateStatus(String(workflow.current_state.status ?? ""))}
          </span>

          <span>
            Progress: {String(workflow.current_state.progress ?? 0)}%
          </span>
        </div>
      </div>
    ) : null}

    {workflow.optimization ? (
      <div className="card">
        <h3>Optimization</h3>

        <p>{workflow.optimization.summary}</p>

        <div className="meta-row">
          <span>
            Critical path:{" "}
            {(() => {
              const path = workflow.optimization.critical_path ?? [];
              if (!path.length) return "—";
              const names = path.map((id: string) => {
                const t = (workflow.tasks ?? []).find((task: any) => task.id === id);
                return t ? t.title || t.description : id;
              });
              return names.join(" → ");
            })()}
          </span>

          <span>
            Estimated effort:{" "}
            {effortLabel(
              (workflow.optimization.critical_path_effort ?? 0) >= 4
                ? "large"
                : (workflow.optimization.critical_path_effort ?? 0) >= 2
                  ? "medium"
                  : "small",
            )}
          </span>
        </div>
      </div>
    ) : null}

    <div className="card">
      <h3>Plan</h3>

      {workflow.plan_validation ? (
        <div className="meta-row">
          <span>
            {validationLabel(workflow.plan_validation.valid)}:{" "}
            {workflow.plan_validation.summary}
          </span>

          {workflow.plan_validation.errors?.length ? (
            <span>
              Errors: {workflow.plan_validation.errors.length}
            </span>
          ) : null}

          {workflow.plan_validation.warnings?.length ? (
            <span>
              Warnings: {workflow.plan_validation.warnings.length}
            </span>
          ) : null}
        </div>
      ) : null}

      <table className="task-table">
        <thead>
          <tr>
            <th>Status</th>
            <th>Task</th>
            <th>Effort</th>
            <th>Dependencies</th>
          </tr>
        </thead>

        <tbody>
          {tasks.length === 0 ? (
            <tr>
              <td colSpan={4} className="muted">
                No tasks in the plan.
              </td>
            </tr>
          ) : (
            tasks.map((task: any) => {
              const taskStatusClass = `status status-${task.status}`;
              return (
                <tr key={task.id}>
                  <td>
                    <span className={taskStatusClass}>
                    {taskStatusLabel(task.status)}
                    </span>
                  </td>

                  <td>
                    <span className="muted task-ref" title={task.id}>{task.id.replace(/^task_/, "").padStart(2, "0")}</span>{" "}
                    <span className="task-title">{task.title || task.description}</span>
                    {task.title && task.description !== task.title ? (
                      <div className="muted task-desc">{task.description}</div>
                    ) : null}
                  </td>

                  <td>{effortLabel(task.effort)}</td>

                  <td className="muted">
                    {(task.dependencies ?? []).map((dep: string) => dep.replace(/^task_/, "")).join(", ") || "—"}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>

    {workflow.detected_blockers?.length ? (
      <div className="card">
        <h3>Blockers</h3>

        <ul className="plain-list">
          {workflow.detected_blockers.map(
            (blocker: any, index: number) => (
              <li key={`${blocker.task_id ?? "blocker"}-${index}`}>
                <code>{blocker.task_id || "plan"}</code>: {blocker.message}
              </li>
            ),
          )}
        </ul>
      </div>
    ) : null}

    {workflow.memory_context?.length ? (
      <div className="card">
        <h3>Memory context</h3>

        <ul className="plain-list">
          {workflow.memory_context.map(
            (line: string, index: number) => (
              <li key={`memory-${index}`}>{line}</li>
            ),
          )}
        </ul>
      </div>
    ) : null}
  </section>

  );
}

function HistoryPage() {
  const [workflows, setWorkflows] =
  useState<WorkflowSummary[] | null>(null);

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
  let cancelled = false;

  (async () => {
    try {
      const data = await listWorkflowsRequest();

      if (!cancelled) {
        setWorkflows(data);
      }
    } catch (reason) {
      if (!cancelled) {
        setError(
          reason instanceof Error ? reason.message : String(reason),
        );
      }
    }
  })();

  return () => {
    cancelled = true;
  };

  }, []);

  if (error) {
    return (
      <section className="page">
      <h1>History</h1>
      <ErrorBanner message={error} />
      </section>
    );
  }

  if (!workflows) {
    return <Loading />;
  }

  return (
    <section className="page">
    <p className="eyebrow">YOUR WORKSPACE</p>
    <h1>Projects</h1>
    <p className="lede">Pick up where you left off or open a project to review its plan and documents.</p>

    {workflows.length === 0 ? (
      <div className="card empty-state"><h2>No projects yet</h2><p>Create a project to get a tailored action plan.</p><button className="primary" onClick={() => navigate("")}>Create a project →</button></div>
    ) : (
      <div className="project-grid">
        {workflows.map((workflow) => {
          const progress = workflow.total_tasks === 0 ? 0 : Math.round((workflow.completed_tasks / workflow.total_tasks) * 100);
          const isProcessing = workflow.execution_state === "queued" || workflow.execution_state === "running";
          return (
            <button key={workflow.workflow_id} type="button" className="project-card" onClick={() => navigate(`workflow/${encodeURIComponent(workflow.workflow_id)}`)}>
              <span className="project-card-top">
                    <span className="project-status">{priorityLabel(workflow.priority)}</span>
                    <span className={`status status-${workflow.execution_state}`}>{executionStatusLabel(workflow.execution_state)}</span>
              </span>
              <strong>{workflow.title || workflow.goal}</strong>
              {isProcessing ? (
                <span className="project-card-meta">Building your plan…</span>
              ) : (
                <span className="project-card-meta">{workflow.completed_tasks} of {workflow.total_tasks} actions complete</span>
              )}
              <span className="project-progress-track"><span style={{ width: `${progress}%` }} /></span>
              <span className="project-card-next">{workflow.recommendation_action ?? "Open project"}<span aria-hidden="true"> →</span></span>
            </button>
          );
        })}
      </div>
    )}
  </section>

  );
}

function AboutPage() {
  return (
    <section className="page">
    <h1>About</h1>

    <div className="card">
      <p>
        ActionPlan is an advisory AI workplace operations agent. Describe a
        project goal and it organizes the work into an actionable plan:
        analyzing the objective, extracting organizational requirements and
        procedures, retrieving relevant evidence from your indexed documents,
        and validating an execution order.
      </p>

      <p>
        As work progresses it tracks completion, detects blockers, and
        recommends the next action. When project circumstances change, you can
        supply updates and the agent will reassess the plan.
      </p>

      <p>
        The agent is advisory-only: it never executes external actions
        automatically. Every recommendation is a suggestion for your team to
        review, accept, or reject. Accepted recommendations can then be sent
        explicitly to Slack or Jira when those integrations are configured.
      </p>
    </div>
  </section>

  );
}

export default function App() {
  const route = useHashRoute();

  const [backendStatus, setBackendStatus] =
  useState<BackendStatus>("checking");

  useEffect(() => {
  let cancelled = false;

  (async () => {
    try {
      const status = await checkBackendHealth();

      if (!cancelled) {
        setBackendStatus(status);
      }
    } catch {
      if (!cancelled) {
        setBackendStatus("error");
      }
    }
  })();

  const interval = setInterval(async () => {
    try {
      const status = await checkBackendHealth();
      setBackendStatus(status);
    } catch {
      setBackendStatus("error");
    }
  }, 30000);

  return () => {
    cancelled = true;
    clearInterval(interval);
  };

  }, []);

  const workflowMatch = matchRoute(route, "workflow/:id");

  let content: React.ReactNode;

  if (!route) {
  content = <HomePage />;
  } else if (route === "history") {
  content = <HistoryPage />;
  } else if (route === "about") {
  content = <AboutPage />;
  } else if (workflowMatch) {
  content = (
    <WorkflowPage workflowId={workflowMatch.params.id} />
  );
  } else {
  content = (
    <section className="page">
    <h1>Page not found</h1>

      <div className="card">
        The route <code>#{route}</code> does not exist.{" "}
        <button type="button" onClick={() => navigate("")}>
          Go to new request
        </button>
      </div>
    </section>
  );
  }

  return (
    <Layout activeWorkflows={Boolean(workflowMatch)} backendStatus={backendStatus} >
    {content}
    </Layout>
  );
}
