import { useEffect, useState } from "react";

import { continueGoalRequest, createGoalRequest, getWorkflowRequest, listWorkflowsRequest } from "./api/client";
import type { WorkflowSummary } from "./api/workflow-types";
import { matchRoute, navigate, useHashRoute } from "./lib/useHashRoute";

function Layout({
  children,
  activeWorkflows,
}: {
  children: React.ReactNode;
  activeWorkflows?: boolean;
}) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#/">
          Workplace Operations Agent
        </a>
        <nav className="nav">
          <button type="button" onClick={() => navigate("")}>
            New Request
          </button>
          <button type="button" onClick={() => navigate("history")}>
            History
          </button>
          <button type="button" onClick={() => navigate("about")}>
            About
          </button>
          {activeWorkflows ? (
            <span className="nav-badge">active workflows</span>
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
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!goal.trim()) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const workflow = await createGoalRequest({ goal: goal.trim() });
      window.location.hash = `#/workflow/${workflow.workflow_id}`;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      setSubmitting(false);
    }
  }

  return (
    <section className="page">
      <h1>Create an action plan</h1>
      <p className="lede">
        Describe the work you need done. The agent will analyze the objective,
        extract requirements, plan and validate an execution order, and
        recommend the next action - without executing anything automatically.
      </p>
      <form className="card form" onSubmit={handleSubmit}>
        <label className="field">
          <span>Goal</span>
          <textarea
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder="e.g. Prepare Project Alpha for production"
            rows={4}
            required
          />
        </label>
        {error ? <ErrorBanner message={error} /> : null}
        <button type="submit" className="primary" disabled={submitting}>
          {submitting ? "Analyzing…" : "Analyze goal"}
        </button>
      </form>
    </section>
  );
}

function WorkflowPage({ workflowId }: { workflowId: string }) {
  const [workflow, setWorkflow] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getWorkflowRequest(workflowId);
        if (!cancelled) {
          setWorkflow(data);
        }
      } catch (reason) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      }
    })();
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

  if (error) {
    return (
      <section className="page">
        <h1>Workflow</h1>
        <ErrorBanner message={error} />
      </section>
    );
  }
  if (!workflow) {
    return <Loading />;
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
        </div>
      ) : null}

      {workflow.current_state ? (
        <div className="card">
          <h3>Current state</h3>
          <div className="meta-row">
            <span>Status: {String(workflow.current_state.status ?? "—")}</span>
            <span>Progress: {String(workflow.current_state.progress ?? 0)}%</span>
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
                {(workflow.optimization.critical_path ?? []).join(" → ") || "—"}
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
              <span>Errors: {workflow.plan_validation.errors.length}</span>
            ) : null}
            {workflow.plan_validation.warnings?.length ? (
              <span>Warnings: {workflow.plan_validation.warnings.length}</span>
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
              tasks.map((task: any) => (
                <tr key={task.id}>
                  <td>
                    <span className={`status status-${task.status}`}>
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
              ))
            )}
          </tbody>
        </table>
      </div>

      {workflow.detected_blockers?.length ? (
        <div className="card">
          <h3>Blockers</h3>
          <ul className="plain-list">
            {workflow.detected_blockers.map((blocker: any, index: number) => (
              <li key={`${blocker.task_id ?? "blocker"}-${index}`}>
                <code>{blocker.task_id || "plan"}</code>: {blocker.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {workflow.memory_context?.length ? (
        <div className="card">
          <h3>Memory context</h3>
          <ul className="plain-list">
            {workflow.memory_context.map((line: string, index: number) => (
              <li key={`memory-${index}`}>{line}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function HistoryPage() {
  const [workflows, setWorkflows] = useState<WorkflowSummary[] | null>(null);
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
          setError(reason instanceof Error ? reason.message : String(reason));
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
      <h1>Workflow history</h1>
      {workflows.length === 0 ? (
        <div className="card muted">No workflows yet.</div>
      ) : (
        <table className="task-table">
          <thead>
            <tr>
              <th>Workflow</th>
              <th>Goal</th>
              <th>Progress</th>
              <th>Recommendation</th>
            </tr>
          </thead>
          <tbody>
            {workflows.map((workflow) => {
              const progress =
                workflow.total_tasks === 0
                  ? 0
                  : Math.round(
                      (workflow.completed_tasks / workflow.total_tasks) * 100,
                    );
              return (
                <tr
                  key={workflow.workflow_id}
                  onClick={() =>
                    navigate(`workflow/${workflow.workflow_id}`)
                  }
                  className="clickable"
                >
                  <td>
                    <code>{workflow.workflow_id}</code>
                  </td>
                  <td>{workflow.goal}</td>
                  <td>
                    {workflow.completed_tasks}/{workflow.total_tasks} ({progress}
                    %)
                  </td>
                  <td className="muted">
                    {workflow.recommendation_action ?? "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
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
          This is an advisory AI workplace operations agent. It analyzes a work
          request, extracts organizational requirements and procedures, builds
          and validates an execution plan, detects blockers, and recommends the
          next action.
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

  const workflowMatch = matchRoute(route, "workflow/:id");
  let content: React.ReactNode;
  if (!route) {
    content = <HomePage />;
  } else if (route === "history") {
    content = <HistoryPage />;
  } else if (route === "about") {
    content = <AboutPage />;
  } else if (workflowMatch) {
    content = <WorkflowPage workflowId={workflowMatch.params.id} />;
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
    <Layout activeWorkflows={Boolean(workflowMatch)}>{content}</Layout>
  );
}