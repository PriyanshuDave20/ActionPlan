# Plan: Make plan generation logic and output more natural and professional

## Goal

The plan the app produces (backend logic + frontend rendering) should read like it was written by a competent colleague, not a deterministic engine. Specifically:

- **Backend generation:** task titles/descriptions, phase names, and the plan `rationale` should use natural, plain language; avoid robotic meta-talk ("classified as ...", "organized by the deterministic dependency engine").
- **Frontend output:** stop leaking raw backend strings (`Priority: high`, `Deadline pressure: ...`, `Validation: valid`, status chips like `in_progress`, bare section headings "Plan"/"Blockers"/"Memory context"). Use human-readable labels, sentence-case copy, and a short plan summary/intro.

## Scope — files to change

**Backend (plan generation logic):**
1. `backend/app/llm/provider.py:777-824` (`build_work_breakdown` prompt) — refine instructions so the LLM emits natural task phrasing, consistent phase names, and a plain-language rationale; keep the concrete BAD/GOOD example style.
2. `backend/app/agent/planning_engine.py:237-245` (`repair_breakdown` rationale) — replace the robotic rationale with a natural summary mentioning phase/task count and organizing principle.
3. `backend/app/agent/nodes/work_breakdown.py:61-66` — softer, user-facing failure rationale.

**Frontend (plan output):**
4. `frontend/src/App.tsx:86-136` — add label maps for priority, validation result, and task status (mirroring existing `effortLabel`/`actionLabel`).
5. `frontend/src/App.tsx:479-520` (recommendation card) — human-readable priority/deadline labels; keep the `reason` but present it cleanly.
6. `frontend/src/App.tsx:572-644` (plan table) — add a plan summary/intro line from `candidate_plan.rationale`, friendlier validation chip, friendly status chips, descriptive section heading.
7. `frontend/src/App.tsx:538-570` (optimization) and `646-674` (blockers/memory) — softer headings and copy.

**Out of scope:** no new export/email/PDF features, no backend model/schema changes, no LLM provider changes.

## Validation

- Backend: run `pytest` in `backend/` — focus on `tests/unit/test_planning_engine.py`, `tests/unit/test_models.py`, `tests/unit/test_validation_optimization.py`, `tests/integration/test_api.py`, `tests/integration/test_workflow.py`. Deterministic plan logic must still pass (cycle breaking, ID repair, topological order, approval safeguard).
- Frontend: TypeScript compile / Vite build if tooling is available; otherwise review types manually against `frontend/src/api/workflow-types.ts`.

## Approach notes

- The deterministic engine (cycle repair, ID normalization, topological order, approval-coverage safeguard) stays untouched — only the user-facing strings/rationale change.
- Backend changes are string-only; no contract changes to `CandidatePlan`/`CandidateTask`/`WorkBreakdown`.
- Frontend changes are view-layer only; no API contract changes.

Next step: I need your approval before implementing. Once approved, I'll make the edits and run the test suite.