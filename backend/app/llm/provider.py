import json
import logging
from typing import Any, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.models.frames import ObjectiveAnalysis, ProcedureExtraction
from app.models.project_spec import (
    EvidenceRef,
    PlannedTaskDraft,
    ProjectSpecification,
    SpecItem,
    WorkBreakdown,
    WorkPackageDraft,
)
from app.models.requirement import Requirement, RequirementExtraction
from app.models.work_request import WorkRequest


logger = logging.getLogger(__name__)

# Retrieval-context markers used by the deterministic mock extractor: a
# chunk whose text mentions one of these is routed to the matching spec
# section. The real LLM performs the same classification with full context.
_SPEC_MARKERS: dict[str, tuple[str, ...]] = {
    "objective": ("objective", "aim", "purpose of this project", "we propose"),
    "research_questions": ("research question", "hypothesis", "we investigate", "we compare"),
    "scope": ("scope", "in this project we", "we will analyze"),
    "methodology": ("method", "approach", "pipeline", "we use", "dataset"),
    "major_activities": ("step", "activity", "we will", "first", "then", "analyze", "compare", "identify"),
    "deliverables": ("deliverable", "final report", "presentation", "report will"),
    "milestones": ("milestone", "week", "by the end", "deadline", "due"),
    "constraints": ("constraint", "must not", "limitation", "only use"),
    "resources": ("resource", "available", "provided", "dataset", "server"),
    "people": ("team", "student", "advisor", "responsib", "sanna", "priyanshu"),
    "deadlines": ("deadline", "due", "submit", "by december", "timeline"),
    "evaluation_criteria": ("graded", "evaluation", "assessed", "criteria", "rubric"),
    "dependencies": ("depends on", "requires", "prerequisite", "after"),
    "risks": ("risk", "if the", "may fail", "fallback", "limitation"),
}

# Upper bound on tokens generated for any single structured-output call.
# The schemas used by this agent produce at most a few hundred tokens, so
# this only ever truncates runaway output (e.g. a model looping on the
# schema) instead of constraining legitimate answers.
MAX_OUTPUT_TOKENS = 2048


class LLMProvider(Protocol):
    def chat(self, prompt: str) -> str:
        ...

    def chat_json(self, prompt: str, schema: type[BaseModel], retries: int = 2) -> BaseModel:
        ...

    def analyze_objective(self, work_request: WorkRequest) -> ObjectiveAnalysis:
        ...

    def extract_procedures(self, work_request: WorkRequest) -> ProcedureExtraction:
        ...

    def extract_requirements(self, work_request: WorkRequest) -> RequirementExtraction:
        ...

    def understand_documents(self, goal: str, context: str) -> ProjectSpecification:
        ...

    def build_work_breakdown(self, spec: ProjectSpecification, requirements: list[Requirement], evidence: str) -> WorkBreakdown:
        ...


class MockLLMProvider:
    """Deterministic provider for local development and tests."""

    def chat(self, prompt: str) -> str:
        return f"Mock response for: {prompt}"

    def chat_json(self, prompt: str, schema: type[BaseModel], retries: int = 2) -> BaseModel:
        """Deterministic mock implementation of ``chat_json``.

        Parses the embedded ``WorkRequest`` from the prompt when possible and
        returns a schema-compatible instance. Never calls external services.
        """
        work_request = self._work_request_from_prompt(prompt)
        people = work_request.people if work_request else []
        roles = work_request.roles if work_request else []
        current_status = work_request.current_status if work_request else None
        success_criteria = work_request.success_criteria if work_request else None
        constraints = work_request.constraints if work_request else None
        resources = work_request.resources if work_request else None
        deadline = work_request.deadline if work_request else None
        priority = work_request.priority if work_request else "medium"
        goal = work_request.goal if work_request else "the stated goal"

        if schema is ObjectiveAnalysis:
            return ObjectiveAnalysis(
                objective=(
                    f"Determine and complete the requirements necessary "
                    f"to achieve: {goal}"
                ),
                current_situation=(
                    current_status
                    or "Initial state. Work has not been defined yet."
                ),
                success_criteria=(
                    success_criteria
                    or ["Success criteria confirmed with the requester"]
                ),
                constraints=(
                    constraints
                    or ["No explicit constraints provided; clarify before execution"]
                ),
                stakeholders=[person.name for person in people] or ["Task owner"],
                decision_makers=list(roles) or ["Requesting manager"],
                external_dependencies=(
                    resources
                    or ["No external dependencies were listed"]
                ),
                timeline_flags=[
                    f"Deadline: {deadline.isoformat()}"
                    if deadline
                    else "No explicit deadline set"
                ],
                priority_flags=[f"Priority: {priority}"],
                notes="Objective analysis generated by the deterministic mock provider.",
            )
        if schema is ProcedureExtraction:
            return ProcedureExtraction(
                summary=(
                    "No procedure documents were indexed for this goal, so "
                    "execution relies on defined requirements and approvals."
                ),
                procedures=[],
                notes=[
                    "Ingest organizational procedure documents to ground execution.",
                ],
            )
        if schema is RequirementExtraction:
            return RequirementExtraction(
                requirements=[
                    Requirement(
                        id="req_1",
                        category="process",
                        text="Define the sequence of work needed to reach the objective",
                        rationale="Work must be broken into an ordered, executable sequence.",
                        relevant_tasks=["task_1"],
                    ),
                    Requirement(
                        id="req_2",
                        category="policy",
                        text="Identify the organizational policies that govern this work",
                        rationale="Policies determine what is permitted and required.",
                        relevant_tasks=["task_2"],
                    ),
                    Requirement(
                        id="req_3",
                        category="approval",
                        text="Obtain approval from decision makers before finalizing changes",
                        rationale="Changes need authorized sign-off before execution.",
                        relevant_tasks=["task_3"],
                    ),
                    Requirement(
                        id="req_4",
                        category="evidence",
                        text="Confirm that success criteria and required information are available",
                        rationale="Evidence must be available to verify completion.",
                        relevant_tasks=["task_4"],
                    ),
                ]
            )
        raise ValueError(f"MockLLMProvider.chat_json does not support schema {schema.__name__}")

    def _work_request_from_prompt(self, prompt: str) -> WorkRequest | None:
        """Best-effort extraction of a ``WorkRequest`` embedded in the prompt.

        The structured prompt appends ``work_request.model_dump_json()`` after
        the scenario label. If it cannot be parsed, return ``None`` and the
        caller falls back to defaults.
        """
        import json
        import re

        match = re.search(r"\{.*\}", prompt, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return WorkRequest(**data)
        except Exception:
            return None

    def analyze_objective(self, work_request: WorkRequest) -> ObjectiveAnalysis:
        return ObjectiveAnalysis(
            objective=(
                f"Determine and complete the requirements necessary "
                f"to achieve: {work_request.goal}"
            ),
            current_situation=(
                work_request.current_status
                or "Initial state. Work has not been defined yet."
            ),
            success_criteria=(
                work_request.success_criteria
                or ["Success criteria confirmed with the requester"]
            ),
            constraints=(
                work_request.constraints
                or ["No explicit constraints provided; clarify before execution"]
            ),
            stakeholders=[person.name for person in work_request.people] or ["Task owner"],
            decision_makers=[role for role in work_request.roles] or [
                "Requesting manager"
            ],
            external_dependencies=(
                work_request.resources
                or ["No external dependencies were listed"]
            ),
            timeline_flags=[
                f"Deadline: {work_request.deadline.isoformat()}"
                if work_request.deadline
                else "No explicit deadline set"
            ],
            priority_flags=[f"Priority: {work_request.priority}"],
            notes="Objective analysis generated by the deterministic mock provider.",
        )

    def extract_procedures(self, work_request: WorkRequest) -> ProcedureExtraction:
        return ProcedureExtraction(
            summary=(
                "No procedure documents were indexed for this goal, so "
                "execution relies on defined requirements and approvals."
            ),
            procedures=[],
            notes=[
                "Ingest organizational procedure documents to ground execution.",
            ],
        )

    def extract_requirements(self, work_request: WorkRequest) -> RequirementExtraction:
        return RequirementExtraction(
            requirements=[
                Requirement(
                    id="req_1",
                    category="process",
                    text="Define the sequence of work needed to reach the objective",
                    rationale="Work must be broken into an ordered, executable sequence.",
                    relevant_tasks=["task_1"],
                ),
                Requirement(
                    id="req_2",
                    category="policy",
                    text="Identify the organizational policies that govern this work",
                    rationale="Policies determine what is permitted and required.",
                    relevant_tasks=["task_2"],
                ),
                Requirement(
                    id="req_3",
                    category="approval",
                    text="Obtain approval from decision makers before finalizing changes",
                    rationale="Changes need authorized sign-off before execution.",
                    relevant_tasks=["task_3"],
                ),
                Requirement(
                    id="req_4",
                    category="evidence",
                    text="Confirm that success criteria and required information are available",
                    rationale="Evidence must be available to verify completion.",
                    relevant_tasks=["task_4"],
                ),
            ]
        )

    # -- Document-grounded planning -------------------------------------

    def understand_documents(self, goal: str, context: str) -> ProjectSpecification:
        """Deterministic spec extraction for local development and tests.

        Parses the structured retrieval context embedded in the prompt (each
        chunk is delivered as a fenced JSON line) and derives the spec from
        it. When no document content is present the specification stays
        essentially empty and ``missing_information`` records what is
        unknown — nothing is fabricated.
        """
        chunks = self._parse_context_chunks(context)
        spec = ProjectSpecification(title=goal, project_type="general")

        def add(section: str, text: str, document: str, page: int | None) -> None:
            getattr(spec, section).append(
                SpecItem(
                    content=text,
                    source=EvidenceRef(document=document, page=page),
                    confidence=0.9,
                    kind="explicit",
                )
            )

        lowered_batches = []
        for chunk in chunks:
            text = chunk["text"].lower()
            document = chunk["document"]
            page = chunk["page"]
            for section, markers in _SPEC_MARKERS.items():
                for marker in markers:
                    if marker in text:
                        add(section, chunk["text"][:240], document, page)
                        break
            lowered_batches.append(text)

        if chunks:
            spec.search_queries = [goal] + [chunk["text"][:60] for chunk in chunks[:3]]
        else:
            spec.missing_information = [
                "No project documents were provided; scope, methodology, deliverables, deadlines and responsibilities are unspecified.",
            ]
        return spec

    def build_work_breakdown(
        self,
        spec: ProjectSpecification,
        requirements: list[Requirement],
        evidence: str,
    ) -> WorkBreakdown:
        """Deterministic breakdown for local development and tests.

        Grounded in the specification: tasks mirror the extracted major
        activities and cover the extracted deliverables. With no document
        evidence it falls back to four goal-scoped starter tasks so the
        mock path keeps its historical shape.
        """
        requirement_ids = [requirement.id for requirement in requirements]
        approval_requirement = next(
            (requirement.id for requirement in requirements if requirement.category == "approval"),
            None,
        )

        activities = [item.content for item in spec.major_activities]
        deliverables = [item.content for item in spec.deliverables]

        tasks: list[PlannedTaskDraft] = []
        if activities:
            for index, activity in enumerate(activities, start=1):
                tasks.append(
                    PlannedTaskDraft(
                        id=f"task_{index}",
                        title=activity,
                        description=f"{activity} (from project documents).",
                        completion_criteria=[f"{activity} completed and reviewed."],
                        deliverable=deliverables[index - 1] if index <= len(deliverables) else None,
                        deliverable_refs=[str(index - 1)] if index <= len(deliverables) else [],
                        dependencies=[f"task_{index - 1}"] if index > 1 else [],
                        effort="medium",
                        priority="high" if index == 1 else "medium",
                        phase="phase_1",
                        evidence_passages=[item.source.passage for item in spec.major_activities if item.content == activity][:1],
                        requirement_ids=[requirement_ids[(index - 1) % len(requirement_ids)]] if requirement_ids else [],
                    )
                )
            if approval_requirement and not any(
                approval_requirement in task.requirement_ids for task in tasks
            ):
                tasks.append(
                    PlannedTaskDraft(
                        id=f"task_{len(tasks) + 1}",
                        title="Obtain stakeholder approval for completed work",
                        description="Secure documented sign-off from the decision makers identified for this project.",
                        completion_criteria=["Written approval recorded."],
                        dependencies=[tasks[-1].id] if tasks else [],
                        effort="small",
                        priority="high",
                        phase="phase_1",
                        requirement_ids=[approval_requirement],
                    )
                )
        else:
            goal = spec.title or "the project"
            starter = [
                ("Clarify scope and success criteria", f"Confirm the scope, success criteria and constraints for {goal}."),
                ("Draft the work plan", f"Break {goal} into ordered work packages with owners."),
                ("Execute the core work", f"Carry out the main work required for {goal}."),
                ("Review outcomes and close out", f"Verify outcomes against the success criteria for {goal} and record sign-off."),
            ]
            for index, (title, description) in enumerate(starter, start=1):
                tasks.append(
                    PlannedTaskDraft(
                        id=f"task_{index}",
                        title=title,
                        description=description,
                        completion_criteria=[f"{title} completed for {goal}."],
                        dependencies=[f"task_{index - 1}"] if index > 1 else [],
                        effort="medium" if index in (2, 3) else "small",
                        priority="medium",
                        phase="phase_1",
                        requirement_ids=[requirement_ids[(index - 1) % len(requirement_ids)]] if requirement_ids else [],
                    )
                )

        phases = [
            WorkPackageDraft(
                id="phase_1",
                name="Delivery" if activities else "Project delivery",
                description="Work derived from the project specification.",
                task_ids=[task.id for task in tasks],
            )
        ]
        return WorkBreakdown(
            project_type=spec.project_type,
            phases=phases,
            tasks=tasks,
            assumptions=[item.content for item in spec.constraints][:3],
            open_questions=list(spec.missing_information),
        )

    def _parse_context_chunks(self, context: str) -> list[dict]:
        """Parse the fenced JSON chunk lines used in retrieval prompts."""
        chunks: list[dict] = []
        for line in context.splitlines():
            line = line.strip()
            if not (line.startswith("{") and line.endswith("}")):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "text" in data:
                chunks.append(
                    {
                        "text": str(data.get("text", "")),
                        "document": str(data.get("document", "")),
                        "page": data.get("page"),
                    }
                )
        return chunks


_SCHEMA_NOISE_KEYS = frozenset(
    {"title", "description", "default", "minLength", "maxLength", "minimum", "maximum"}
)


def _extract_json(content: str) -> str:
    """Extract the first balanced JSON object (or array) from model output.

    Tolerates Markdown code fences, prose around the JSON, and stray
    characters before or after the JSON document. The returned substring
    is guaranteed balanced with respect to braces/brackets inside strings.
    """
    if not content:
        raise json.JSONDecodeError("empty model response", content, 0)

    text = content.strip()
    if text.startswith("```"):
        newline = text.find("\n")
        if newline != -1:
            text = text[newline + 1 :]
        if text.endswith("```"):
            text = text[: -len("```")].strip()

    start = text.find("{")
    if start == -1:
        start = text.find("[")
    if start == -1:
        raise json.JSONDecodeError(
            "model response contains no JSON object or array", content, 0
        )

    open_char = text[start]
    close_char = "}" if open_char == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise json.JSONDecodeError("unbalanced JSON in model response", content, start)


def _trim_schema(node: Any) -> Any:
    """Return the JSON schema without prompt-bloating and echo-baiting noise.

    ``model_json_schema()`` is verbose: every field carries ``title``,
    ``description``, ``default``, and length constraints that do nothing but
    enlarge the prompt and encourage small models to echo the schema instead
    of producing data. We drop those keys and keep structure, types, enums,
    ``$defs`` and ``required``.

    Keys are only stripped at the schema level, never inside a ``properties``
    map, because a *field* may legitimately be named ``description`` or
    ``title`` (``ProcedureOption.description`` is one such required field).
    """
    if isinstance(node, dict):
        result: dict[str, Any] = {}
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                result[key] = {
                    field_name: _trim_schema(field_schema)
                    for field_name, field_schema in value.items()
                }
            elif key not in _SCHEMA_NOISE_KEYS:
                result[key] = _trim_schema(value)
        return result
    if isinstance(node, list):
        return [_trim_schema(item) for item in node]
    return node


def _example_value(
    node: dict, defs: dict, depth: int = 0, seen: frozenset[str] = frozenset()
) -> Any:
    """Build a small, structurally valid example object from a JSON schema.

    The example teaches the model the expected nesting and shape so it
    produces data rather than echoing the schema. Arrays get one sample
    element so nested objects are illustrated. ``seen`` guards against
    self-referential schemas.
    """
    if depth > 12:
        return {}
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        if name in seen:
            return {}
        return _example_value(defs.get(name, {}), defs, depth + 1, seen | {name})
    if "anyOf" in node:
        alternatives = [alt for alt in node.get("anyOf", []) if alt.get("type") != "null"]
        if alternatives:
            return _example_value(alternatives[0], defs, depth, seen)
    node_type = node.get("type")
    if node_type == "object":
        return {
            name: _example_value(child, defs, depth + 1, seen)
            for name, child in (node.get("properties") or {}).items()
        }
    if node_type == "array":
        items = node.get("items") or {}
        return [_example_value(items, defs, depth + 1, seen)]
    if node_type == "boolean":
        return True
    if node_type == "integer" or node_type == "number":
        return 1
    if node.get("enum"):
        return node["enum"][0]
    return "example"


def _build_instruction(schema: type[BaseModel]) -> str:
    schema_node = _trim_schema(schema.model_json_schema())
    schema_json = json.dumps(schema_node, indent=2)
    example_json = json.dumps(
        _example_value(schema_node, schema_node.get("$defs", {})), indent=2
    )
    return (
        "You are a precise senior workplace operations planner.\n"
        "\n"
        "Respond with ONE JSON object that holds REAL DATA about the scenario.\n"
        "\n"
        "SCHEMA (field structure only - do NOT copy the schema itself):\n"
        f"{schema_json}\n"
        "\n"
        "EXAMPLE of a valid POPULATED response (keep this shape, fill with real content):\n"
        f"{example_json}\n"
        "\n"
        "HARD RULES:\n"
        "- Your entire reply is a single JSON object starting with '{' and ending with '}'.\n"
        "- Return the POPULATED data. Never output a schema. Never include the words\n"
        "  'schema', '$defs', 'properties', 'required', or 'title' inside the JSON.\n"
        "- Do not use Markdown code fences, comments, or any text outside the JSON.\n"
        "- Use empty lists for fields where no items are known.\n"
    )


class SchemaEchoError(ValueError):
    """The model returned a JSON Schema document instead of populated data."""


# Keys that only ever appear in a JSON Schema document, never in a populated
# instance of the response models this agent uses.
_SCHEMA_ONLY_KEYS = frozenset(
    {"$defs", "definitions", "$schema", "properties", "type", "additionalProperties"}
)


def _reject_schema_echo(parsed: object, schema: type[BaseModel]) -> None:
    """Fail fast when the model echoes the schema instead of returning data.

    Models whose fields are all optional (``RequirementExtraction``) would
    otherwise *accept* a schema echo as a valid but empty object, silently
    producing zero requirements/tasks with no error. Pydantic ignores extra
    keys by default, so explicit detection is required.
    """
    if not isinstance(parsed, dict):
        return
    field_names = set(schema.model_fields)
    echoed = _SCHEMA_ONLY_KEYS & set(parsed)
    if echoed and not (set(parsed) & field_names):
        raise SchemaEchoError(
            "model returned a JSON schema (keys: "
            + ", ".join(sorted(echoed))
            + ") instead of populated data"
        )


def _error_summary(error: Exception) -> str:
    """Return a safe, one-line description of a parse/validation failure.

    Pydantic ``ValidationError`` may embed the offending (possibly user-echoed)
    ``input``; we deliberately exclude input values and schema URLs so no
    sensitive content or credentials are ever logged.
    """
    if isinstance(error, ValidationError):
        parts = []
        for item in error.errors(include_input=False, include_url=False):
            location = ".".join(str(part) for part in item.get("loc", ()))
            parts.append(f"{location}: {item.get('msg', str(item.get('type', '')))}")
        return "[validation error] " + ("; ".join(parts) or str(error))
    return f"[{type(error).__name__}] {error}"


class LangChainStructuredProvider:
    """
    Structured LLM provider built on an OpenAI-compatible chat model
    (NVIDIA NIM, OpenRouter, vLLM, OpenAI).
    """

    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    def chat(self, prompt: str, max_tokens: int | None = None) -> str:
        if max_tokens is not None and max_tokens != MAX_OUTPUT_TOKENS:
            # Per-call override: large schemas (e.g. the work breakdown)
            # legitimately need more room than the global default cap.
            response = self.llm.bind(max_tokens=max_tokens).invoke(prompt)
        else:
            response = self.llm.invoke(prompt)
        content = response.content
        if isinstance(content, str):
            return content
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
            else:
                parts.append(str(part))
        return "".join(parts)

    def chat_json(
        self,
        prompt: str,
        schema: type[BaseModel],
        retries: int = 2,
        max_tokens: int | None = None,
    ) -> BaseModel:
        instruction = _build_instruction(schema)
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            raw = self.chat(instruction + "\n\n" + prompt, max_tokens=max_tokens)
            try:
                parsed = json.loads(_extract_json(raw))
                _reject_schema_echo(parsed, schema)
                return schema.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError, SchemaEchoError) as error:
                last_error = error
                summary = _error_summary(error)
                logger.warning(
                    "LLM JSON parse/validation failed (schema=%s attempt=%s/%s): %s",
                    schema.__name__,
                    attempt + 1,
                    retries + 1,
                    summary,
                )
                instruction = (
                    instruction
                    + "\nYour previous response was rejected:\n"
                    + summary
                    + "\n\nSend ONLY a corrected JSON object now. Start it with '{' and end it "
                    "with '}'. Include every field named in the SCHEMA above with real content "
                    "for this scenario. Do NOT output a schema, and do NOT return an empty "
                    "object or empty lists unless there is genuinely nothing to report."
                )

        raise RuntimeError(f"LLM returned invalid structured output: {_error_summary(last_error)}")

    def analyze_objective(self, work_request: WorkRequest) -> ObjectiveAnalysis:
        result = self.chat_json(
            "Work request (populate the ObjectiveAnalysis for this scenario):\n"
            f"{work_request.model_dump_json()}\n"
            "Analyze the objective, current situation, dependencies, timeline "
            "and priority of the work described above.",
            ObjectiveAnalysis,
        )
        if not isinstance(result, ObjectiveAnalysis):
            raise RuntimeError("analyze_objective returned the wrong schema")
        return result

    def extract_procedures(self, work_request: WorkRequest) -> ProcedureExtraction:
        result = self.chat_json(
            "Work request (populate the ProcedureExtraction for this scenario):\n"
            f"{work_request.model_dump_json()}\n"
            "Identify organizational procedures that apply to this work. "
            "If none are known, return an empty procedures list.",
            ProcedureExtraction,
        )
        if not isinstance(result, ProcedureExtraction):
            raise RuntimeError("extract_procedures returned the wrong schema")
        return result

    def extract_requirements(self, work_request: WorkRequest) -> RequirementExtraction:
        result = self.chat_json(
            "Work request (populate the RequirementExtraction for this scenario):\n"
            f"{work_request.model_dump_json()}\n"
            "Extract the organizational requirements (process, policy, "
            "approval, evidence) that this work must satisfy. Use stable "
            "requirement IDs such as req_1, req_2.",
            RequirementExtraction,
        )
        if not isinstance(result, RequirementExtraction):
            raise RuntimeError("extract_requirements returned the wrong schema")
        return result

    # -- Document-grounded planning -------------------------------------

    def understand_documents(self, goal: str, context: str) -> ProjectSpecification:
        prompt = (
            "Project goal:\n"
            f"{goal}\n\n"
            "Retrieved project-document excerpts (one JSON object per line; "
            "document and page identify the source):\n"
            f"{context}\n\n"
            "Extract a structured specification of the project described by "
            "these documents. Rules:\n"
            "- Every item MUST cite the document, page and a short supporting "
            "passage it came from. Do not invent facts.\n"
            "- Mark an item 'inference' only when you derive it from explicit "
            "content; otherwise 'explicit'.\n"
            "- If deadlines, budget, methodology or responsibilities are not "
            "stated anywhere, list them under missing_information instead of "
            "guessing.\n"
            "- Classify the project into exactly one type: academic_research, "
            "software_development, business_initiative, "
            "operational_improvement, event_planning, product_development, "
            "or general.\n"
            "- Include 3-8 search_queries that would retrieve good coverage "
            "of the underlying documents.\n"
            "- Extract the concrete major activities the project requires, "
            "in the project's own terms."
        )
        result = self.chat_json(
            prompt,
            ProjectSpecification,
            # Many document chunks produce a large spec; the default cap
            # truncates the JSON mid-object.
            max_tokens=4096,
        )
        if not isinstance(result, ProjectSpecification):
            raise RuntimeError("understand_documents returned the wrong schema")
        return result

    def build_work_breakdown(
        self,
        spec: ProjectSpecification,
        requirements: list[Requirement],
        evidence: str,
    ) -> WorkBreakdown:
        spec_json = spec.model_dump_json()
        requirements_json = json.dumps(
            [{"id": r.id, "category": r.category, "text": r.text} for r in requirements]
        )
        prompt = (
            "PROJECT SPECIFICATION (extracted from the project's own "
            "documents; every item cites its source):\n"
            f"{spec_json}\n\n"
            "ORGANIZATIONAL REQUIREMENTS that must be respected:\n"
            f"{requirements_json}\n\n"
            "SUPPORTING EVIDENCE retrieved for these requirements:\n"
            f"{evidence}\n\n"
            "Produce a hierarchical work breakdown for THIS project:\n"
            "- 2-6 phases (work packages) appropriate to the project type.\n"
            "- Tasks that are specific to this project's actual activities, "
            "objectives and deliverables. A person must know exactly what to "
            "do from the title alone. BAD: 'Complete project research'. "
            "GOOD: 'Compare wild-type and R168C binding-site motifs'.\n"
            "- Ground every task in the specification; where a task relies on "
            "document content, quote the passage in evidence_passages.\n"
            "- Reference spec deliverables by their zero-based list index in "
            "deliverable_refs and restate them in deliverable.\n"
            "- Propose dependencies between tasks using their ids; only "
            "declare a dependency when the output of one task is genuinely "
            "an input of the other.\n"
            "- Use qualitative effort (small/medium/large). Do not invent "
            "durations the documents do not support.\n"
            "- Tag tasks with requirement_ids when they satisfy an "
            "organizational requirement (approvals must be tagged).\n"
            "- List assumptions and open questions separately. Do not expand "
            "the project scope beyond the documents."
        )
        result = self.chat_json(
            prompt,
            WorkBreakdown,
            # The breakdown is the largest structured output in the system;
            # the global cap truncates it mid-JSON on long documents.
            max_tokens=4096,
        )
        if not isinstance(result, WorkBreakdown):
            raise RuntimeError("build_work_breakdown returned the wrong schema")
        return result


def create_llm_provider(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider.lower().strip()

    if provider in {"nvidia", "openai", "openai-compatible"}:
        from langchain_openai import ChatOpenAI

        model = settings.resolved_llm_model
        api_key = settings.resolved_llm_api_key
        base_url = settings.resolved_llm_base_url

        if not model:
            raise ValueError("LLM_MODEL is required for cloud LLM providers.")
        if not api_key:
            raise ValueError("LLM_API_KEY is required for cloud LLM providers.")
        if not base_url:
            raise ValueError("LLM_BASE_URL is required for cloud LLM providers.")

        llm_kwargs = {
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": 0,
            "timeout": 900,
            "max_retries": 0,
# Cap generation so a confused model cannot ramble for tens of
        # seconds (and blow past the Lambda timeout) echoing the schema.
        # These structured outputs need at most a few hundred tokens.
        #
        # NOTE: this must be sent via ``extra_body``. langchain-openai
        # 0.3.x unconditionally rewrites a top-level ``max_tokens`` into
        # ``max_completion_tokens`` (see ChatOpenAI._default_params), a
        # parameter NVIDIA's OpenAI-compatible endpoint does not accept.
        # ``extra_body`` is merged verbatim into the JSON request body by
        # the OpenAI SDK, so the wire payload keeps the standard
        # ``max_tokens`` field.
        "extra_body": {
            "max_tokens": MAX_OUTPUT_TOKENS,
        },
    }

    # NVIDIA Nemotron models need explicit thinking disabled for structured output
    if provider == "nvidia":
        llm_kwargs["extra_body"]["chat_template_kwargs"] = {"enable_thinking": False}

    llm = ChatOpenAI(**llm_kwargs)
    return LangChainStructuredProvider(llm)

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        model = getattr(settings, "ollama_model", None)
        if not model:
            raise ValueError("OLLAMA_MODEL is required when LLM_PROVIDER=ollama.")
        return LangChainStructuredProvider(
            ChatOllama(model=model, base_url=settings.ollama_base_url)
        )

    if provider == "mock":
        return MockLLMProvider()

    raise ValueError(
        f"Unsupported LLM_PROVIDER: {provider}. "
        "Expected one of: nvidia, openai, openai-compatible, ollama, mock."
    )
