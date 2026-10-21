import { useEffect, useState } from "react";

import {
  continueGoalRequest,
  createGoalRequest,
  getWorkflowRequest,
  listWorkflowsRequest,
  checkBackendHealth,
  ingestDocumentRequest,
  refreshWorkflowRequest,
  decideRecommendationRequest,
  pollWorkflowUntilComplete,
  getWorkflowStatusRequest,
  type BackendStatus,
} from "./api/client";
import type { WorkflowSummary } from "./api/workflow-types";
import { matchRoute, navigate, useHashRoute } from "./lib/useHashRoute";

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

function HomePage() {
  const [goal, setGoal] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);
  const [createdWorkflowId, setCreatedWorkflowId] = useState<string | null>(null);
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
      let workflowId = createdWorkflowId;
      if (!workflowId) {
        setProgress("Creating project…");
        // Async: returns immediately with queued workflow
        const workflow = await createGoalRequest({ goal: goal.trim() }, false);
        workflowId = workflow.workflow_id;
        setCreatedWorkflowId(workflowId);
      }

      if (workflowId) {
        setProgress("Building your project plan…");
        const workflow = await pollWorkflowUntilComplete(workflowId, (state) => {
          setProgress(`Building your project plan… (${state.execution_state})`);
        });
        
        if (workflow.execution_state === "failed") {
          throw new Error(workflow.execution_error || "Workflow execution failed");
        }
        
        workflowId = workflow.workflow_id;
        setCreatedWorkflowId(workflowId);
      }

      const remainingFiles = files.filter((file) => !uploadedFiles.includes(file.name));
      for (let index = 0; index < remainingFiles.length; index += 1) {
        const file = remainingFiles[index];
        setProgress(`Adding document ${index + 1} of ${remainingFiles.length}…`);
        await ingestDocumentRequest(file, workflowId);
        setUploadedFiles((current) => [...current, file.name]);
      }

      if (remainingFiles.length > 0) {
        setProgress("Updating the plan with your documents…");
        await refreshWorkflowRequest(workflowId);
      }
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
          <span>What are you working on?</span>

          <textarea
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder="e.g. Prepare Project Alpha for production by coordinating launch readiness, approvals, and team handoffs."
            rows={4}
            disabled={submitting || Boolean(createdWorkflowId)}
            required
          />
        </label>

        <div className="initial-documents">
          <div>
            <span className="field-title">Project documents <span className="optional-label">Optional</span></span>
            <p className="muted">Add policies, briefs, or reference files now. They'll be ingested before your project opens.</p>
          </div>
          <label className={`button secondary initial-upload ${submitting ? "disabled" : ""}`}>
            <span aria-hidden="true">＋</span> Choose files
            <input
              type="file"
              accept=".pdf,.txt,.md,.csv"
              multiple
              disabled={submitting || Boolean(createdWorkflowId)}
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
                  {uploadedFiles.includes(file.name) ? <span className="file-ready">Added</span> : null}
                  {!submitting && !createdWorkflowId ? <button type="button" aria-label={`Remove ${file.name}`} onClick={() => setFiles((current) => current.filter((item) => item.name !== file.name))}>×</button> : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        {error ? <ErrorBanner message={error} /> : null}

        <button type="submit" className="primary" disabled={submitting}>
          {submitting ? (progress || "Creating project…") : createdWorkflowId ? "Retry document setup" : "Create project →"}
        </button>
        {createdWorkflowId && error ? <button type="button" className="button secondary" onClick={() => { window.location.hash = `#/workflow/${createdWorkflowId}`; }}>Open project anyway</button> : null}
      </form>
    </section>
  );
}

function WorkflowPage({ workflowId }: { workflowId: string }) {
  const [workflow, setWorkflow] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);
  const [documents, setDocuments] = useState<string[]>([]);
  const [executionState, setExecutionState] = useState<string>("queued");

  useEffect(() => {
    let cancelled = false;

    const pollWorkflow = async () => {
      try {
        const statusData = await getWorkflowStatusRequest(workflowId);
        
        if (cancelled) return;

        setExecutionState(statusData.execution_state);

        if (statusData.execution_state === "queued" || statusData.execution_state === "running") {
          // Still processing, poll again
          setTimeout(pollWorkflow, 1000);
          return;
        }

        // Workflow completed or failed, fetch full data
        const data = await getWorkflowRequest(workflowId);
        
        if (!cancelled) {
          setWorkflow(data);
          setDocuments(data.execution_metadata?.documents ?? []);
          // events and evidence not used in current UI
        }
      } catch (reason) {
        if (!cancelled) {
          setError(
            reason instanceof Error ? reason.message : String(reason),
          );
        }
      }
    };

    pollWorkflow();

    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  async function handleContinue() {
    if (!workflow) {
      return;
    }
    setCompleting(true);
    setError(null);

    try {
      const next = await continueGoalRequest(
        workflow.workflow_id,
        workflow.completed_tasks ?? [],
      );

      setWorkflow(next);
      setCompleting(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      setCompleting(false);
    }
  }

async function decide(decision: string) {
    if (!workflow?.recommendation?.recommendation_id) return;
    try { setWorkflow(await decideRecommendationRequest(workflow.workflow_id, workflow.recommendation.recommendation_id, decision, workflow.version)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  }

  if (error) {
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
return (
      <section className="page">
      <div className="card">
        <div className="meta-row">
          <div className="status status-checking">
            <span className="status-dot"></span>
            <span>{executionState === "queued" ? "Queued..." : executionState === "running" ? "Building your project plan..." : executionState === "needs_review" ? "Awaiting review..." : "Loading..."}</span>
          </div>
        </div>
      </div>
      <p className="muted">This may take a minute while we analyze your project and build the plan.</p>
      </section>
    );
  }

  const tasks = workflow.tasks ?? [];

  const pending = tasks.filter(
    (task: any) => task.status !== "completed",
  );

  return (
    <section className="page">
    <div className="workflow-head">
    <div>
    <h1>{workflow.original_goal}</h1>
    <span className="muted mono">{workflow.workflow_id}</span>
    </div>

      <button
        type="button"
        className="primary"
        onClick={handleContinue}
        disabled={completing || pending.length === 0}
      >
        {completing
          ? "Updating…"
          : pending.length === 0
            ? "All tasks complete"
            : "Continue workflow"}
      </button>
    </div>

    <div className="card documents-card">
      <div className="section-title-row">
        <div><p className="eyebrow">PROJECT KNOWLEDGE</p><h2>Documents</h2></div>
      </div>
      <p className="muted">Reference files added during project setup.</p>
      {documents.length ? <ul className="document-list">{documents.map((name) => <li key={name}><span className="document-icon">↳</span>{name}</li>)}</ul> : <p className="empty-inline">No documents added yet.</p>}
    </div>
    {error ? <ErrorBanner message={error} /> : null}

    {workflow.recommendation ? (
      <div className="card recommendation-card">
        <h2>
          Recommended next action:{" "}
          <code>{workflow.recommendation.action}</code>
        </h2>

        <p>{workflow.recommendation.reason}</p>

        <div className="meta-row">
          <span>
            Affected task:{" "}
            <code>{workflow.recommendation.affected_task ?? "—"}</code>
          </span>

          <span>Priority: {workflow.recommendation.priority}</span>

          <span>
            Deadline pressure: {workflow.recommendation.deadline_pressure}
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
        </div>
      </div>
    ) : null}

    {workflow.current_state ? (
      <div className="card">
        <h3>Current state</h3>

        <div className="meta-row">
          <span>
            Status: {String(workflow.current_state.status ?? "—")}
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
            <code>
              {(workflow.optimization.critical_path ?? []).join(" → ") ||
                "—"}
            </code>
          </span>

          <span>
            Effort: {workflow.optimization.critical_path_effort ?? 0} units
          </span>
        </div>
      </div>
    ) : null}

    <div className="card">
      <h3>Plan</h3>

      {workflow.plan_validation ? (
        <div className="meta-row">
          <span>
            Validation:{" "}
            {workflow.plan_validation.valid ? "valid" : "invalid"} -{" "}
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
                      {task.status}
                    </span>
                  </td>

                  <td>
                    <code>{task.id}</code> {task.description}
                  </td>

                  <td>{task.effort}</td>

                  <td className="muted">
                    {(task.dependencies ?? []).join(", ") || "—"}
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
          return (
            <button key={workflow.workflow_id} type="button" className="project-card" onClick={() => navigate(`workflow/${encodeURIComponent(workflow.workflow_id)}`)}>
              <span className="project-card-top"><span className="project-status">{workflow.priority} priority</span><span className="project-progress">{progress}%</span></span>
              <strong>{workflow.goal}</strong>
              <span className="project-card-meta">{workflow.completed_tasks} of {workflow.total_tasks} actions complete</span>
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
        This is an advisory AI workplace operations agent. It analyzes a
        work request, extracts organizational requirements and procedures,
        builds and validates an execution plan, detects blockers, and
        recommends the next action.
      </p>

      <p>
        The agent never executes actions automatically: every recommendation
        is advisory and should be reviewed by people.
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