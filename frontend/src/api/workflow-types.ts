export type EffortLevel = "small" | "medium" | "large" | "high";
export type Priority = "low" | "medium" | "high";
export type TaskStatus = "pending" | "in_progress" | "completed" | "blocked";
export type RequirementCategory =
  | "policy"
  | "process"
  | "approval"
  | "evidence"
  | "definition";

export interface Person {
  name: string;
  role: string;
}

export interface WorkRequestInput {
  goal: string;
  people_involved?: Person[];
  deadline?: string | null;
  priority?: Priority;
  current_status?: string | null;
  constraints?: string[];
  resources?: string[];
  success_criteria?: string[];
}

export interface WorkRequest {
  goal: string;
  people: Person[];
  roles: string[];
  deadline: string | null;
  priority: Priority;
  current_status: string | null;
  constraints: string[];
  resources: string[];
  success_criteria: string[];
}

export interface Evidence {
  content: string;
  source: string | null;
  page: number | null;
  document_type: string | null;
}

export interface Requirement {
  id: string;
  category: RequirementCategory;
  text: string;
  rationale: string | null;
  relevant_tasks: string[];
  covered: boolean;
}

export interface CandidateTask {
  task_id: string;
  description: string;
  requirement_id: string | null;
  procedure_id: string | null;
  effort: EffortLevel;
  dependencies: string[];
}

export interface CandidatePlan {
  rationale: string;
  assumptions: string[];
  tasks: CandidateTask[];
}

export interface ValidationIssue {
  code: string;
  message: string;
  task_id: string | null;
}

export interface PlanValidationResult {
  valid: boolean;
  summary: string;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  invalid_dependencies: string[];
  missing_approvals: string[];
  sequencing_violations: string[];
  uncovered_requirements: string[];
  revision_count: number;
}

export interface Task {
  id: string;
  description: string;
  dependencies: string[];
  status: TaskStatus;
  effort: EffortLevel;
  role: string | null;
  owner: string | null;
  mandatory: boolean;
  required_information: string[];
  required_approvals: string[];
  requirement_ids: string[];
  procedure_sources: string[];
  evidence: Evidence[];
}

export interface ProcedureOption {
  command: string;
  description: string;
  flags: string[];
}

export interface ProcedureStep {
  order: number;
  action: string;
  required_information: string[];
  optional: boolean;
  options: ProcedureOption[];
}

export interface Procedure {
  id: string;
  name: string;
  source: string | null;
  summary: string | null;
  steps: ProcedureStep[];
}

export interface BlockedTask {
  task_id: string;
  reason: string;
  plan: string[];
  evidence: Evidence[];
}

export interface Recommendation {
  action: string;
  reason: string;
  priority: string;
  affected_task: string | null;
  blocked_by: string | null;
  requirement_id: string | null;
  role: string | null;
  critical_path: string[];
  deadline_pressure: string;
  evidence: string[];
}

export interface OptimizationResult {
  summary: string;
  critical_path: string[];
  critical_path_effort: number;
  parallel_chains: string[][];
  days_until_deadline: number | null;
  deadline_feasible: boolean | null;
  deadline_notes: string | null;
  notes: string[];
}

export interface ObjectiveAnalysis {
  objective: string;
  current_situation: string | null;
  success_criteria: string[];
  constraints: string[];
  stakeholders: string[];
  decision_makers: string[];
  external_dependencies: string[];
  timeline_flags: string[];
  priority_flags: string[];
  notes: string | null;
}

export interface Blocker {
  task_id: string;
  type: string;
  message: string;
}

/** Response of POST /goals and GET /workflows/{id}. Mirrors WorkflowState. */
export interface WorkflowState {
  workflow_id: string;
  original_goal: string;
  work_request: WorkRequest | null;
  objective_analysis: ObjectiveAnalysis | null;
  goal_analysis: Record<string, unknown> | null;
  planner_steps: string[];
  procedure_analysis: Record<string, unknown> | null;
  procedures: Procedure[];
  requirements: Requirement[];
  candidate_plan: CandidatePlan | null;
  plan_validation: PlanValidationResult | null;
  plan_revision_count: number;
  optimization: OptimizationResult | null;
  tasks: Task[];
  completed_tasks: string[];
  blocked_tasks: string[];
  current_task: string | null;
  current_state: Record<string, unknown>;
  retrieved_documents: Evidence[];
  detected_blockers: Blocker[];
  recommendation: Recommendation | null;
  memory_context: string[];
  execution_metadata: Record<string, unknown>;
}

export interface WorkflowSummary {
  workflow_id: string;
  goal: string;
  updated_at: string;
  deadline: string | null;
  priority: Priority;
  total_tasks: number;
  completed_tasks: number;
  blocker_count: number;
  recommendation_action: string | null;
}

export interface IngestResponse {
  filename: string;
  chunks: number;
}