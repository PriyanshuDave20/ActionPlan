"""End-to-end flow test for the AI Workplace Operations Agent.

Runs the complete LangGraph workflow for a fixed objective and asserts the
full output shape, then exercises GET/continue/list/ingest on the real
routes. Uses a stubbed OpenAI-compatible endpoint by default, so it makes
NO network calls and costs nothing. Pass --live to hit the real provider.

Usage:
    py -3 scripts/test_flow.py
    py -3 scripts/test_flow.py --live
"""

import argparse
import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

GOAL = "Prepare Project Alpha"

SCHEMA_ECHO = json.dumps(
    {
        "$defs": {
            "Procedure": {
                "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
                "required": ["id", "name"],
                "type": "object",
            }
        },
        "properties": {
            "summary": {"type": "string"},
            "procedures": {"type": "array"},
            "notes": {"type": "array"},
        },
        "required": ["summary"],
        "title": "ProcedureExtraction",
        "type": "object",
    }
)

VALID_PROCEDURES = json.dumps(
    {
        "summary": "Alpha launch follows the standard release procedure.",
        "procedures": [
            {
                "id": "proc_1",
                "name": "Release readiness review",
                "source": "indexed policy",
                "summary": "Confirm the checklist before promoting the build.",
                "steps": [
                    {
                        "order": 1,
                        "action": "Complete the readiness checklist",
                        "required_information": ["checklist"],
                        "optional": False,
                        "options": [
                            {
                                "command": "run-readiness",
                                "description": "Run the readiness suite",
                                "flags": ["--strict"],
                            }
                        ],
                    }
                ],
            }
        ],
        "notes": ["Grounded in an indexed policy document."],
    }
)

VALID_OBJECTIVE = json.dumps(
    {
        "objective": "Prepare Project Alpha for production release",
        "current_situation": "Alpha is feature-complete but not yet promoted.",
        "success_criteria": ["Alpha is live for customers"],
        "constraints": ["Security review must pass first"],
        "stakeholders": ["Release lead"],
        "decision_makers": ["Engineering manager"],
        "external_dependencies": ["Security review"],
        "timeline_flags": ["No explicit deadline set"],
        "priority_flags": ["Priority: high"],
        "notes": None,
    }
)

VALID_REQUIREMENTS = json.dumps(
    {
        "requirements": [
            {
                "id": "req_1",
                "category": "process",
                "text": "Sequence the work needed to reach the objective",
                "rationale": "Work must be ordered.",
                "relevant_tasks": ["task_1"],
            },
            {
                "id": "req_2",
                "category": "policy",
                "text": "Obtain approval from decision makers",
                "rationale": "Changes need sign-off.",
                "relevant_tasks": ["task_2"],
            },
        ]
    }
)


class StubNIM:
    """Mimics the previous NVIDIA failure: echo the schema once, then comply.

    Returning a schema echo on the first attempt for every schema reproduces
    the exact bug that was fixed, so this test fails loudly if schema-echo
    recovery regresses.
    """

    def __init__(self):
        self.calls = []
        self.echoed = set()

    def response_for(self, prompt: str) -> str:
        if "ProcedureExtraction" in prompt:
            key, valid = "ProcedureExtraction", VALID_PROCEDURES
        elif "RequirementExtraction" in prompt:
            key, valid = "RequirementExtraction", VALID_REQUIREMENTS
        else:
            key, valid = "ObjectiveAnalysis", VALID_OBJECTIVE

        if key not in self.echoed:
            self.echoed.add(key)
            return SCHEMA_ECHO  # replicate the original bug
        return valid

    def __call__(self, request) -> "httpx.Response":
        import httpx

        body = json.loads(request.content.decode())
        prompt = body["messages"][0]["content"]
        self.calls.append(prompt)
        return httpx.Response(
            200,
            json={
                "id": f"chatcmpl-{len(self.calls)}",
                "object": "chat.completion",
                "created": 0,
                "model": "meta/llama-3.2-11b-vision-instruct",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": self.response_for(prompt),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
        )


def build_app(live: bool):
    """Create the FastAPI app backed by either a stub or the real LLM."""
    import os

    if not live:
        os.environ["LLM_PROVIDER"] = "nvidia"  # exercise the real code path
        os.environ["LLM_MODEL"] = "meta/llama-3.2-11b-vision-instruct"
        os.environ["LLM_BASE_URL"] = "https://integrate.api.nvidia.com/v1"
        os.environ.setdefault("LLM_API_KEY", "stub-key-not-real")

    os.environ["EMBEDDING_PROVIDER"] = "mock"
    os.environ["VECTOR_STORE"] = "in-memory"
    os.environ["MEMORY_BACKEND"] = "local"

    stub = None
    if not live:
        from fastapi.testclient import TestClient

        from langchain_openai import ChatOpenAI

        import httpx

        from app.llm.provider import MAX_OUTPUT_TOKENS, LangChainStructuredProvider

        # Patch provider construction so every route uses the stub transport.
        import app.api.dependencies as deps

        stub = StubNIM()
        llm = ChatOpenAI(
            model="meta/llama-3.2-11b-vision-instruct",
            api_key="stub-key-not-real",
            base_url="https://integrate.api.nvidia.com/v1",
            temperature=0,
            timeout=120,
            max_retries=0,
            extra_body={"max_tokens": MAX_OUTPUT_TOKENS},
            http_client=httpx.Client(transport=httpx.MockTransport(stub)),
        )
        deps.create_llm_provider = lambda settings: LangChainStructuredProvider(llm)

        from app.main import app

        return app, TestClient(app), stub

    from app.main import app

    from fastapi.testclient import TestClient

    return app, TestClient(app), stub


class Checks:
    def __init__(self):
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name, condition, detail=""):
        ok = bool(condition)
        self.results.append((name, ok, detail))
        print(f"  [{'OK ' if ok else 'FAIL'}] {name}" + (f"  {detail}" if not ok else ""))
        return ok

    def report(self) -> int:
        failed = [r for r in self.results if not r[1]]
        print(f"\n{len(self.results) - len(failed)}/{len(self.results)} checks passed")
        return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="use the real NVIDIA LLM")
    args = parser.parse_args()

    with TemporaryDirectory() as tmp:
        import os

        os.environ["DATA_DIR"] = tmp

        print(f"Flow test - objective: {GOAL!r} (live={args.live})\n")
        app, client, stub = build_app(args.live)
        c = Checks()

        # --- health -----------------------------------------------------
        r = client.get("/health")
        c.check("GET /health -> 200", r.status_code == 200, str(r.status_code))
        c.check("health payload ok", r.json() == {"status": "ok"}, r.text[:120])

        # --- create the workflow (full LangGraph run) --------------------
        started = time.perf_counter()
        r = client.post(
            "/goals",
            json={
                "goal": GOAL,
                "people_involved": [{"name": "Ada", "role": "lead"}],
                "priority": "high",
                "success_criteria": ["Alpha is live"],
            },
        )
        elapsed = time.perf_counter() - started
        c.check("POST /goals -> 201", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
        if r.status_code != 201:
            return c.report()

        body = r.json()
        workflow_id = body.get("workflow_id", "")
        print(f"\n  workflow_id={workflow_id}  ({elapsed:.2f}s)\n")

        # --- workflow shape ----------------------------------------------
        expected_top = [
            "blocked_tasks", "candidate_plan", "completed_tasks", "current_state",
            "current_task", "detected_blockers", "execution_metadata",
            "memory_context", "objective_analysis", "optimization",
            "original_goal", "plan_revision_count", "plan_validation",
            "procedure_analysis", "procedures", "recommendation",
            "requirements", "tasks", "work_request", "workflow_id",
        ]
        missing = [k for k in expected_top if k not in body]
        c.check("workflow top-level keys present", not missing, f"missing={missing}")
        c.check("workflow_id present", bool(workflow_id))
        c.check("original_goal echoed", body.get("original_goal") == GOAL, body.get("original_goal", ""))

        # --- the LLM actually produced data, not a schema ----------------
        proc_analysis = body.get("procedure_analysis") or {}
        c.check(
            "procedure_analysis.summary is real prose",
            isinstance(proc_analysis.get("summary"), str)
            and "alpha" in proc_analysis.get("summary", "").lower()
            and "properties" not in proc_analysis.get("summary", "").lower(),
            repr(proc_analysis.get("summary"))[:160],
        )
        c.check(
            "procedure_analysis.count matches procedures",
            proc_analysis.get("count") == len(body.get("procedures") or []),
            f"count={proc_analysis.get('count')} len={len(body.get('procedures') or [])}",
        )

        procedures = body.get("procedures") or []
        c.check("procedures extracted (nested objects survived)", len(procedures) >= 1, f"n={len(procedures)}")
        if procedures:
            proc = procedures[0]
            c.check("procedure has id/name", bool(proc.get("id")) and bool(proc.get("name")), str(proc)[:120])
            steps = proc.get("steps") or []
            c.check("procedure steps present", len(steps) >= 1, f"n={len(steps)}")
            if steps:
                step = steps[0]
                c.check("step order/action present", bool(step.get("order")) and bool(step.get("action")), str(step)[:120])
                opts = step.get("options") or []
                c.check(
                    "nested option keeps required 'description' field",
                    bool(opts) and bool(opts[0].get("description")),
                    f"options={str(opts)[:160]}",
                )

        obj = body.get("objective_analysis") or {}
        c.check("objective_analysis populated", len(obj) >= 5, f"n={len(obj)}")
        c.check(
            "objective_analysis has no schema keys",
            not ({"properties", "$defs", "required"} & set(obj)),
            f"keys={sorted(obj)[:12]}",
        )
        c.check("objective field is prose", isinstance(obj.get("objective"), str) and len(obj.get("objective", "")) > 10, repr(obj.get("objective"))[:120])

        reqs = body.get("requirements") or []
        c.check("requirements extracted", len(reqs) >= 1, f"n={len(reqs)}")
        if reqs:
            valid_cats = {"policy", "process", "approval", "evidence", "definition"}
            c.check("requirement category valid", reqs[0].get("category") in valid_cats, reqs[0].get("category"))
            c.check("requirement id/text present", bool(reqs[0].get("id")) and bool(reqs[0].get("text")), str(reqs[0])[:120])

        # --- deterministic graph outputs ---------------------------------
        tasks = body.get("tasks") or []
        c.check("tasks generated", len(tasks) >= 1, f"n={len(tasks)}")
        if tasks:
            t = tasks[0]
            c.check("task id not task_id", "id" in t and "task_id" not in t)
            c.check("task status pending", t.get("status") == "pending", t.get("status"))
            c.check("task effort valid", t.get("effort") in {"small", "medium", "large", "high"}, t.get("effort"))

        pv = body.get("plan_validation") or {}
        c.check("plan_validation produced", "valid" in pv and "summary" in pv, f"keys={sorted(pv)[:8]}")
        opt = body.get("optimization") or {}
        c.check("optimization critical_path present", "critical_path" in opt, f"keys={sorted(opt)[:8]}")
        c.check("current_state progress numeric", isinstance((body.get("current_state") or {}).get("progress"), (int, float)))
        rec = body.get("recommendation") or {}
        c.check("recommendation action valid", rec.get("action") in {"start_task", "await_dependency", "no_action"}, rec.get("action"))
        c.check("memory_context written", len(body.get("memory_context") or []) >= 1, f"n={len(body.get('memory_context') or [])}")

        # --- stub-specific: prove schema-echo recovery happened -----------
        if stub is not None:
            c.check(
                "model echoed the schema (bug reproduced)",
                len(stub.echoed) == 3,
                f"echoed={sorted(stub.echoed)}",
            )
            c.check(
                "each schema needed exactly one corrective retry",
                len(stub.calls) == 6,
                f"llm calls={len(stub.calls)} (3 schemas x 2 attempts)",
            )
            retry_prompts = [p for p in stub.calls if "Your previous response was rejected" in p]
            c.check("retries carried the reason for rejection", len(retry_prompts) == 3, f"n={len(retry_prompts)}")

        # --- read routes ---------------------------------------------------
        r = client.get(f"/workflows/{workflow_id}")
        c.check("GET /workflows/{id} -> 200", r.status_code == 200, str(r.status_code))
        c.check("fetched same workflow", r.json().get("workflow_id") == workflow_id)

        r = client.get("/workflows")
        c.check("GET /workflows -> 200", r.status_code == 200, str(r.status_code))
        summaries = r.json()
        c.check("summary list includes workflow", any(s["workflow_id"] == workflow_id for s in summaries))

        # --- continue the workflow ----------------------------------------
        if tasks:
            r = client.post(
                f"/goals/{workflow_id}/continue",
                json={"completed_task_ids": [tasks[0]["id"]]},
            )
            c.check("POST continue -> 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
            if r.status_code == 200:
                cont = r.json()
                c.check("continue same workflow", cont.get("workflow_id") == workflow_id)
                c.check(
                    "completed task recorded",
                    tasks[0]["id"] in (cont.get("completed_tasks") or []),
                    str(cont.get("completed_tasks")),
                )
                ct = next((t for t in cont.get("tasks", []) if t["id"] == tasks[0]["id"]), None)
                c.check("task now completed", ct is not None and ct.get("status") == "completed", str(ct)[:120])
                c.check(
                    "continue did NOT re-run extraction",
                    len(cont.get("procedures") or []) == len(procedures),
                    f"procedures={len(cont.get('procedures') or [])}",
                )

        # --- documents + error paths ---------------------------------------
        r = client.post(
            "/documents/ingest",
            files={"file": ("policy.txt", b"Review every request before merging.", "text/plain")},
        )
        c.check("POST /documents/ingest -> 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")

        r = client.get("/workflows/wf_does_not_exist")
        c.check("unknown workflow -> 404", r.status_code == 404, str(r.status_code))

        r = client.post("/goals", json={"goal": ""})
        c.check("empty goal -> 422", r.status_code == 422, str(r.status_code))

        if stub is not None:
            wire = [json.loads("{}") for _ in range(0)]
            print(f"\n  LLM calls made: {len(stub.calls)}")
            print(f"  total wall time: {elapsed:.2f}s")

        return c.report()


if __name__ == "__main__":
    raise SystemExit(main())
