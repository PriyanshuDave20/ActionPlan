"""Smoke-test a deployed backend API (local or API Gateway / Lambda).

Verifies the full public contract against a running backend:

    GET  /health
    POST /goals
    GET  /workflows/{workflow_id}
    POST /goals/{workflow_id}/continue  (mirrors /workflows/{id}/continue)

Reads the base URL from the BACKEND_API_URL environment variable. No secrets
are used or required here.

Usage:
    $env:BACKEND_API_URL = "https://<api-id>.execute-api.us-east-2.amazonaws.com"
    py -3 scripts/cloud_smoke_test.py
"""

import os
import sys

import httpx

BASE = os.environ.get("BACKEND_API_URL", "").rstrip("/")
if not BASE:
    sys.exit("BACKEND_API_URL environment variable is required.")

client = httpx.Client(base_url=BASE, timeout=45)
checks = []


def check(name: str, condition: bool, detail: str = "") -> None:
    checks.append((name, bool(condition), detail))


r = client.get("/health")
check("health 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
if r.status_code == 200:
    check("health body ok", r.json().get("status") == "ok", f"body={r.text[:200]}")

r = client.post(
    "/goals",
    json={
        "goal": "Prepare Project Alpha for production",
        "priority": "high",
        "success_criteria": ["Alpha is live"],
    },
)
check("post goals 201", r.status_code == 201, f"status={r.status_code} body={r.text[:300]}")
if r.status_code != 201:
    _report_and_exit()

body = r.json()
workflow_id = body.get("workflow_id")
check("workflow_id present", bool(workflow_id), f"body={str(body)[:200]}")
check("tasks returned", isinstance(body.get("tasks"), list) and len(body["tasks"]) > 0)

r = client.get(f"/workflows/{workflow_id}")
check("get workflow 200", r.status_code == 200, f"status={r.status_code}")
check("get workflow same id", r.json().get("workflow_id") == workflow_id)

task_id = body["tasks"][0]["id"]
r = client.post(f"/goals/{workflow_id}/continue", json={"completed_task_ids": [task_id]})
check("continue 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
if r.status_code == 200:
    check(
        "continue marks task complete",
        task_id in r.json().get("completed_tasks", []),
        f"completed={r.json().get('completed_tasks')}",
    )

_client = httpx.Client(base_url=BASE, timeout=45)
r = _client.post(
    "/documents/ingest",
    files={"file": ("policy.txt", b"Review every request before merging.", "text/plain")},
)
check("ingest 200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
_client.close()
client.close()


def _print() -> None:
    failed = [c for c in checks if not c[1]]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed against {BASE}")
    for name, ok, detail in checks:
        marker = "OK " if ok else "FAIL"
        print(f"  [{marker}] {name} {detail if not ok else ''}")
    if failed:
        raise SystemExit(1)


def _report_and_exit() -> None:
    _print()
    raise SystemExit(1)


_print()