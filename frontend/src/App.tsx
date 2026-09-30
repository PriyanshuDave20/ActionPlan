import { useEffect, useState } from "react";

import {
  continueGoalRequest,
  createGoalRequest,
  getWorkflowRequest,
  listWorkflowsRequest,
  checkBackendHealth,
  ingestDocumentRequest,
  type BackendStatus,
  type IngestResponse,
} from "./api/client";
import type { WorkflowSummary, IngestResponse as IngestResponseType } from "./api/workflow-types";
import { matchRoute, navigate, useHashRoute } from "./lib/useHashRoute";
import { Layout, SidebarNav, SidebarStatus } from "./Layout";

/* Default session metadata – keep whatever the backend already sets */
const sessionEnv: Record<string, string> = {};

export default function App() {
  const route = useHashRoute();
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await checkBackendHealth();
        if (!cancelled) setBackendStatus(status);
      } catch {
        if (!cancelled) setBackendStatus("error");
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
  const page = !route
    ? "home"
    : route === "history"
      ? "history"
      : route === "about"
        ? "about"
        : workflowMatch
          ? "workflow"
          : "unknown";

  /* ----------------------------------------------------------------------
   * Render the correct page component
   * ---------------------------------------------------------------------- */
  let pageContent: React.ReactNode;
  switch (page) {
    case "home":
      pageContent = <HomePage />;
      break;
    case "history":
      pageContent = <HistoryPage />;
      break;
    case "about":
      pageContent = <AboutPage />;
      break;
    case "workflow":
      pageContent = <WorkflowPage workflowId={workflowMatch!.params.id} />;
      break;
    default:
      pageContent = <div>Page not found</div>;
  }

  return (
    <Layout
      page={page}
      backendStatus={backendStatus}
    >
      {pageContent}
    </Layout>
  );
}

/* --------------------------------------------------------------------------
 * Layout – sidebar + main content
 * -------------------------------------------------------------------------- */
function Layout({ page, backendStatus, children }: { page: string; backendStatus: BackendStatus; children: React.ReactNode }) {
  return (
    <div className="app-shell">
      {/* ---------- Sidebar ---------- */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="logo">AP</logo>
          <div>
            <span className="brand-text">ActionPlan</span>
            <span className="subtext">AI Operations Agent</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <SidebarNav
            route={route}
            setRoute={/* no-op – hash changes handled by router */}
            backendStatus={backendStatus}
          />
          <SidebarStatus backendStatus={backendStatus} />
        </nav>
      </aside>

      {/* ---------- Main Content ---------- */}
      <main className="main-content">
        {/* Top utility bar – subtle system info */}
        <section className="util-bar">
          {/* Backend status pill */}
          <span className="status-badge status-{backendStatus === "active" ? "ok" : backendStatus === "error" ? "error" : "checking"}">
            {backendStatus}
          </span>
          {/* Workflow count from history */}
          <span className="muted">
            {page === "history" ? "workflows" : ""}
          </span>
        </section>

        {/* Page content */}
        <section className="page-content">{children}</section>
      </main>
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Sidebar Navigation
 * -------------------------------------------------------------------------- */
function SidebarNav({ route, backendStatus }: { route: string; backendStatus: BackendStatus }) {
  const navLinks = [
    { key: "home", label: "New Request", icon: "↩", exact: "/" },
    { key: "history", label: "Workflows", icon: "📜", exact: "/history" },
    { key: "about", label: "About", icon: "/about" },
  ];

  return (
    <nav>
      {navLinks.map((link) => {
        const isExact = route === link.exact;
        return (
          <button
            key={link.key}
            className={`nav-item ${isExact ? "active" : ""}`}
            onClick={() => navigate(link.exact)}
            aria-current={isExact ? "page" : undefined}
          >
            <span>{link.icon}</span> {link.label}
          </button>
        );
      })}
    </nav>
  );
}

/* --------------------------------------------------------------------------
 * Sidebar System Status
 * -------------------------------------------------------------------------- */
function SidebarStatus({ backendStatus }: { backendStatus: BackendStatus }) {
  const statusMap: Record<BackendStatus, { label: string; color: string }> = {
    checking: { label: "Backend connected", color: var(--muted) },
    active: { label: "Agent online", color: var(--good) },
    error: { label: "Backend error", color: var(--bad) },
    inactive: { label: "Backend idle", color: var(--muted) },
  };

  const { label, color } = statusMap[backendStatus] ?? statusMap.checking;
  return (
    <div className="sidebar-status">
      <span className="status-dot" />
      <span>{label}</span>
    </div>
  );
}

/* --------------------------------------------------------------------------
 * HomePage – premium AI command-center style
 * -------------------------------------------------------------------------- */
function HomePage() {
  const [goal, setGoal] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadedDocuments, setUploadedDocuments] = useState<IngestResponseType[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!goal.trim()) return;
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

  function handleFileChange(file: File | null) {
    setSelectedFile(file);
  }

  async function handleUploadDocument() {
    if (!selectedFile) return;
    setIsUploading(true);
    try {
      const response = await ingestDocumentRequest(selectedFile);
      setUploadedDocuments(prev => [...prev, response]);
      setSelectedFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsUploading(false);
    }
  }

  // Suggestion chips that populate the textarea (no auto-submit)
  const suggestionChips = [
    "Prepare a project for production",
    "Plan a product launch",
    "Organize a cross-team migration",
  ];

  return (
    <section className="page page-home">
      <h1>AI WORKPLACE OPERATIONS</h1>
      <p className="lede">
        Turn complex goals into clear action plans. Describe what you need to
        accomplish and the agent will analyze, extract requirements, build a
        structured workflow, and recommend the next best action.
      </p>

      {/* Goal Input Composer */}
      <div className="card composer-card">
        <h3 style={{ margin: "0 0 12px", fontSize: 14, color: var(--muted) }}>
          What are you trying to accomplish?
        </h3>

        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Describe what you need to accomplish…"
          rows={6}
          className="composer-textarea"
          required
        />
        {/* Suggestion chips under the textarea */}
        <div className="chips" style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 8, fontSize: 13, color: var(--muted) }}>
          {suggestionChips.map((chip) => (
            <button
              key={chip}
              className="chip"
              style={{
                padding: "6px 10px",
                border: "1px solid var(--border)",
                borderRadius: var.radius.md,
                background: "transparent",
                color: var(--muted),
                cursor: "pointer",
                transition: "all var(--transition-fast)",
                whiteSpace: "nowrap",
              }}
              onMouseEnter => (e.target.style.background = "var(--bg-soft)")
              onMouseLeave => (e.target.style.background = "transparent")
              onClick={() => setGoal(goal => goal + (goal ? " " : "") + chip)}
            >
              {chip}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
          <button
            onClick={handleSubmit}
            className="primary"
            disabled={submitting}
          >
            {submitting ? "Analyzing…" : "Analyze goal"}
          </button>
        </div>
      </div>

      {/* "How it works" horizontal sequence */}
      <div className="how-it-works" style={{ marginTop: 24, display: "flex", gap: 24, color: var(--muted), fontSize: 13 }}>
        <div>01 <strong>Understand</strong></div>
        <div>02 <strong>Plan</strong></div>
        <div>03 <strong>Identify blockers</strong></div>
        <div>04 <strong>Recommend</strong></div>
      </div>

      {/* Document upload section */}
      <div className="card" style={{ marginTop: 24, borderColor: var(--accent) }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 13, color: var(--muted) }}>Add documents</h3>
        {isUploading ? (
          <p>Uploading document...</p>
        ) : null}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input
            type="file"
            accept=".pdf, .txt, .docx"
            onChange={(e) => handleFileChange(e.target.files?.[0])}
            style={{ display: "none" }}
            ref={fileRef => fileRef?.click?.()}
          />
          <button
            onClick={() => (fileRef.current?.click?.() || {})}
            style={{
              padding: "6px 12px",
              border: "1px solid var(--border)",
              borderRadius: 8,
              background: "transparent",
              color: var(--text),
              cursor: "pointer",
            }}
          >
            + Add files
          </button>
          {selectedFile && (
            <span style={{ marginLeft: 8, fontSize: 13 }}>
              {selectedFile.name}
              <button
                onClick={() => setSelectedFile(null)}
                style={{ padding: "0", background: "none", border: "none", color: "inherit", cursor: "pointer", title: "Remove" }}
                >×</button>
            </span>
          )}
          {selectedFile && (
            <button
              onClick={handleUploadDocument}
              style={{
                marginLeft: 8,
                padding: "6px 12px",
                border: "1px solid var(--accent)",
                borderRadius: 8,
                background: var(--accent),
                color: white,
                fontSize: 12,
              }}
            >
              Upload
            </button>
          )}
        </div>
        {uploadedDocuments.length > 0 && (
          <div style={{ marginTop: 8, fontSize: 12, color: var(--muted) }}>
            Uploaded: {uploadedDocuments.length} document(s)
            {uploadedDocuments.map((doc, i) => (
              <span key={i} style={{ marginLeft: 12, fontSize: 12 }}>
                {doc.filename} ({doc.chunks} chunks){" "}
              </span>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
 * WorkflowPage – sophisticated workflow command center
 * -------------------------------------------------------------------------- */
function WorkflowPage({ workflowId }: { workflowId: string }) {
  const [workflow, setWorkflow] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getWorkflowRequest(workflowId);
        if (!cancelled) setWorkflow(data);
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      }
    })();
    return () => { cancelled = true; };
  }, [workflowId]);

  async function handleContinue() {
    if (!workflow) return;
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
    return <div className="skeleton" style={{ height: 200 }} />;
  }

  const tasks = workflow.tasks ?? [];
  const pending = tasks.filter((task: any) => task.status !== "completed");

  // Workflow stage order (matching backend architecture)
  const stages = ["ANALYZE", "PLAN", "VALIDATE", "EXECUTE", "OPTIMIZE"];
  const currentStage =
    stages[Math.max(0, Math.min(stages.length - 1, workflow.current_state?.stageIndex ?? 0))];

  return (
    <section className="page page-workflow">
      {/* Top bar: breadcrumb + goal + continue */}
      <div className="workflow-top">
        <nav className="workflow-breadcrumb">
          <span>Workflows</span>
          <span>/</span>
          <span>{workflow.original_goal?.substring(0, 40) || "—"}</span>
        </nav>

        <h1 style={{ margin: "12px 0 8px", fontSize: 20 }}>
          {workflow.original_goal || "—"}
        </h1>

        <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 8 }}>
          <span className="muted" style={{ fontSize: 12 }}>
            {workflow.workflow_id}
          </span>
          { /* Created time if available */ }
          {workflow.updated_at && (
            <span style={{ marginLeft: 8, fontSize: 12, color: var(--muted) }}>
              updated {new Date(workflow.updated_at).toLocaleDateString()}
            </span>
          )}
          {/* Continue workflow primary action */}
          <button
            onClick={handleContinue}
            className="primary"
            disabled={completing || pending.length === 0}
            style={{ fontSize: 13, padding: "6px 12px" }}
          >
            {completing ? "Updating…" : pending.length === 0 ? "All tasks complete" : "Continue workflow"}
          </button>
        </div>
      </div>

      {/* Horizontal workflow progress indicator */}
      <div className="workflow-stages" style={{ margin: "16px 0", display: "flex", gap: 8, alignItems: "center", justifyContent: "center" }}>
        {stages.map((stage, i) => {
          const isCurrent = i === currentStage;
          const isCompleted = i < (workflow.current_state?.stageIndex ?? 0);
          return (
            <div
              key={stage}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 4,
                color: isCompleted ? var(--good) : i <= currentStage ? var(--accent) : var(--muted),
              }}
            >
              <span className="stage-number">{stage}</span>
              <div
                style={{
                  width: 30,
                  height: 4,
                  background: isCompleted
                    ? "var(--good)"
                    : isCurrent
                      ? "var(--accent)"
                      : "var(--border)",
                  borderRadius: 2,
                  transition: "var(--transition-fast)",
                  marginTop: 2,
                }}
              />
            </div>
          );
        })}
      </div>

      {/* Main dashboard grid – two columns */}
      <div className="dashboard-grid" style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 24, marginTop: 24 }}>
        {/* LEFT COLUMN: Primary */ lever:primary
  });
}