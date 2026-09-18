import httpx

BASE = "http://127.0.0.1:8000"
client = httpx.Client(base_url=BASE, timeout=30)

checks = []
def check(name, condition, detail=""):
    checks.append((name, bool(condition), detail))

r = client.get("/health")
check("health 200", r.status_code == 200, f"{r.status_code}")

r = client.post("/goals", json={
    "goal": "Prepare Project Alpha for production",
    "people_involved": [{"name": "Ada", "role": "lead"}],
    "priority": "high",
    "success_criteria": ["Alpha is live"],
})
check("post goals 201", r.status_code == 201, f"{r.status_code}")
body = r.json()

expected_top = [
    "blocked_tasks", "candidate_plan", "completed_tasks", "current_state",
    "current_task", "detected_blockers", "execution_metadata", "goal_analysis",
    "memory_context", "objective_analysis", "optimization", "original_goal",
    "plan_revision_count", "plan_validation", "procedure_analysis",
    "procedures", "recommendation", "requirements", "retrieved_documents",
    "targeted_by_requirement", "targeted_evidence", "tasks", "updated_at",
    "work_request", "workflow_id",
]
missing = [k for k in expected_top if k not in body]
check("workflow top-level keys", not missing, f"missing={missing}")
check("workflow_id present", bool(body.get("workflow_id")))

wr = body.get("work_request") or {}
expected_wr = ["constraints", "current_status", "deadline", "goal", "people",
               "priority", "resources", "roles", "success_criteria"]
check("work_request keys", all(k in wr for k in expected_wr), f"keys={sorted(wr.keys())}")
check("work_request goal", wr.get("goal") == "Prepare Project Alpha for production")

tasks = body.get("tasks") or []
check("tasks non-empty", len(tasks) >= 1, f"n={len(tasks)}")
task = tasks[0]
expected_task = ["dependencies", "description", "effort", "evidence", "id",
                 "mandatory", "owner", "procedure_sources", "required_approvals",
                 "required_information", "requirement_ids", "role", "status"]
check("task keys", all(k in task for k in expected_task), f"keys={sorted(task.keys())}")
check("task id not task_id", "task_id" not in task and "id" in task)
check("task status pending", task.get("status") == "pending", f"{task.get('status')}")
check("effort valid", task.get("effort") in {"small", "medium", "large", "high"})

cp = body.get("candidate_plan") or {}
check("candidate_plan keys", all(k in cp for k in ["assumptions", "rationale", "tasks"]),
      f"keys={sorted(cp.keys())}")

pv = body.get("plan_validation") or {}
expected_pv = ["errors", "invalid_dependencies", "missing_approvals",
               "revision_count", "sequencing_violations", "summary",
               "uncovered_requirements", "valid", "warnings"]
check("plan_validation keys", all(k in pv for k in expected_pv), f"keys={sorted(pv.keys())}")

opt = body.get("optimization") or {}
expected_opt = ["critical_path", "critical_path_effort", "days_until_deadline",
                "deadline_feasible", "deadline_notes", "notes", "parallel_chains",
                "summary"]
check("optimization keys", all(k in opt for k in expected_opt), f"keys={sorted(opt.keys())}")

rec = body.get("recommendation") or {}
expected_rec = ["action", "affected_task", "blocked_by", "critical_path",
                "deadline_pressure", "evidence", "priority", "reason",
                "requirement_id", "role"]
check("recommendation keys", all(k in rec for k in expected_rec), f"keys={sorted(rec.keys())}")
check("recommendation action", rec.get("action") in {"start_task", "await_dependency", "no_action"})

obj = body.get("objective_analysis") or {}
check("objective_analysis count >= 10", len(obj) >= 10, f"n={len(obj)}")

workflow_id = body["workflow_id"]

r = client.get(f"/workflows/{workflow_id}")
check("get workflow 200", r.status_code == 200, f"{r.status_code}")
check("get workflow same id", r.json().get("workflow_id") == workflow_id)

r = client.get("/workflows")
check("list workflows 200", r.status_code == 200, f"{r.status_code}")
summaries = r.json()
check("summaries include workflow", any(s["workflow_id"] == workflow_id for s in summaries))
s0 = summaries[0]
expected_sum = ["blocker_count", "completed_tasks", "deadline", "goal", "priority",
                "recommendation_action", "total_tasks", "updated_at", "workflow_id"]
check("summary keys", all(k in s0 for k in expected_sum), f"keys={sorted(s0.keys())}")

if "id" in task:
    r = client.post(f"/goals/{workflow_id}/continue", json={"completed_task_ids": [task["id"]]})
    check("continue 200", r.status_code == 200, f"{r.status_code}")
    continued = r.json()
    check("continue same workflow", continued.get("workflow_id") == workflow_id)
    check("completed_tasks contains id", task["id"] in continued.get("completed_tasks", []),
          f"ct={continued.get('completed_tasks')}")
    ctask = next((t for t in continued.get("tasks", []) if t["id"] == task["id"]), None)
    check("task status completed", ctask is not None and ctask.get("status") == "completed")

r = client.post(f"/goals/{workflow_id}/continue", json={})
check("continue empty body 200", r.status_code == 200, f"{r.status_code}")

r = client.post("/documents/ingest",
                files={"file": ("policy.txt", b"Review every request before merging.", "text/plain")})
check("ingest 200", r.status_code == 200, f"{r.status_code}")
ing = r.json()
check("ingest keys", all(k in ing for k in ["chunks", "filename"]), f"keys={sorted(ing.keys())}")
check("ingest filename", ing.get("filename") == "policy.txt")

r = client.get("/workflows/wf_missing")
check("unknown workflow 404", r.status_code == 404, f"{r.status_code}")

r = client.post("/goals", json={"goal": ""})
check("empty goal 422", r.status_code == 422, f"{r.status_code}")

failed = [c for c in checks if not c[1]]
print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
for name, ok, detail in checks:
    marker = "OK " if ok else "FAIL"
    print(f"  [{marker}] {name} {detail if not ok else ''}")
if failed:
    raise SystemExit(1)