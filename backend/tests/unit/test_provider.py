import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.llm.provider import (
    MAX_OUTPUT_TOKENS,
    LangChainStructuredProvider,
    MockLLMProvider,
    _build_instruction,
    _example_value,
    _extract_json,
    _reject_schema_echo,
    _trim_schema,
)
from app.models.frames import ObjectiveAnalysis, ProcedureExtraction
from app.models.requirement import RequirementExtraction
from app.models.work_request import WorkRequest, WorkRequestInput, compile_work_request


@pytest.fixture
def provider() -> MockLLMProvider:
    return MockLLMProvider()


def test_mock_chat_returns_deterministic_text(provider):
    assert provider.chat("ping") == "Mock response for: ping"


def test_mock_analyze_objective_shape(provider):
    analysis = provider.analyze_objective(compile_work_request(WorkRequestInput(goal="Ship the product")))
    assert analysis.objective
    assert isinstance(analysis.success_criteria, list)
    assert isinstance(analysis.constraints, list)


def test_mock_extract_procedures_empty(provider):
    extraction = provider.extract_procedures(compile_work_request(WorkRequestInput(goal="Move the office")))
    assert extraction.procedures == []


def test_mock_extract_requirements_returns_four(provider):
    extraction = provider.extract_requirements(
        compile_work_request(
            WorkRequestInput(
                goal="Launch the campaign",
                people_involved=[],
            )
        )
    )
    assert len(extraction.requirements) == 4
    assert [requirement.category for requirement in extraction.requirements] == [
        "process",
        "policy",
        "approval",
        "evidence",
    ]


def test_mock_chat_json_objective_analysis(provider):
    prompt = '{"goal": "Ship the product", "people": [{"name": "Ada", "role": "lead"}], "priority": "high"}'
    result = provider.chat_json(prompt, ObjectiveAnalysis)
    assert isinstance(result, ObjectiveAnalysis)
    assert result.objective
    assert len(result.success_criteria) >= 1


def test_mock_chat_json_procedure_extraction(provider):
    prompt = '{"goal": "Move the office", "people": []}'
    result = provider.chat_json(prompt, ProcedureExtraction)
    assert isinstance(result, ProcedureExtraction)
    assert result.procedures == []


def test_mock_chat_json_requirement_extraction(provider):
    prompt = '{"goal": "Launch the campaign", "people": []}'
    result = provider.chat_json(prompt, RequirementExtraction)
    assert isinstance(result, RequirementExtraction)
    assert len(result.requirements) == 4


def test_mock_chat_json_unsupported_schema(provider):
    class OtherSchema(BaseModel):
        name: str

    with pytest.raises(ValueError, match="does not support schema"):
        provider.chat_json('{"goal": "x"}', OtherSchema)


def test_mock_chat_json_handles_malformed_prompt(provider):
    """When the prompt contains no parseable WorkRequest, the mock falls back
    to defaults instead of crashing."""
    result = provider.chat_json("no json here at all", ObjectiveAnalysis)
    assert isinstance(result, ObjectiveAnalysis)
    assert result.objective


class FakeChatModel:
    """Stands in for a ChatOpenAI instance; returns canned messages."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def invoke(self, prompt):
        self.calls.append(prompt)
        content = self.responses[0]
        if len(self.responses) > 1:
            del self.responses[0]
        return SimpleNamespace(content=content)


def _provider(responses) -> tuple[LangChainStructuredProvider, FakeChatModel]:
    model = FakeChatModel(responses)
    return LangChainStructuredProvider(model), model


def test_extract_json_plain_object():
    raw = '{"summary": "s", "procedures": [], "notes": []}'
    assert json.loads(_extract_json(raw))["summary"] == "s"


def test_extract_json_markdown_fence():
    raw = '```json\n{"summary": "s", "procedures": [], "notes": []}\n```'
    assert json.loads(_extract_json(raw))["summary"] == "s"


def test_extract_json_prose_around():
    raw = 'Sure! Here is the result:\n{"summary": "s", "procedures": [], "notes": []}\nThanks!'
    assert json.loads(_extract_json(raw))["summary"] == "s"


def test_extract_json_brace_inside_string():
    raw = 'a{"summary": "contains } brace", "procedures": [], "notes": []} trailing'
    assert json.loads(_extract_json(raw))["summary"] == "contains } brace"


def test_chat_json_valid_json():
    provider, _ = _provider(['{"summary": "ok", "procedures": [], "notes": []}'])
    result = provider.chat_json("context", ProcedureExtraction)
    assert isinstance(result, ProcedureExtraction)
    assert result.summary == "ok"


def test_chat_json_recovers_from_schema_echo():
    schema_echo = (
        '{"$defs": {"Procedure": {"properties": {}, "type": "object"}}, '
        '"properties": {}, "required": ["summary"], "type": "object"}'
    )
    provider, model = _provider(
        [
            schema_echo,
            '{"summary": "no procedures apply", "procedures": [], "notes": []}',
        ]
    )
    result = provider.chat_json("context", ProcedureExtraction)
    assert result.summary == "no procedures apply"
    assert len(model.calls) == 2
    assert "Your previous response was rejected" in model.calls[1]
    assert "Do NOT output a schema" in model.calls[1]


def test_chat_json_raises_after_all_retries():
    provider, model = _provider(["not json at all"] * 3)
    with pytest.raises(RuntimeError, match="invalid structured output"):
        provider.chat_json("context", ProcedureExtraction)
    assert len(model.calls) == 3


def test_chat_json_rejects_schema_echo_for_optional_field_model():
    """RequirementExtraction has no required fields, so a schema echo would
    otherwise validate as a valid-but-empty result and silently produce zero
    requirements. It must be treated as a failure and retried."""
    schema_echo = '{"$defs": {"Requirement": {"type": "object"}}, "properties": {}, "type": "object"}'
    provider, model = _provider(
        [
            schema_echo,
            json.dumps({"requirements": [{"id": "req_1", "text": "Do the work"}]}),
        ]
    )
    result = provider.chat_json("context", RequirementExtraction)
    assert len(model.calls) == 2
    assert [r.id for r in result.requirements] == ["req_1"]


def test_chat_json_all_echoes_raises_instead_of_returning_empty():
    """Even after retries, never silently return an empty extraction."""
    schema_echo = '{"$defs": {}, "properties": {}, "type": "object"}'
    provider, model = _provider([schema_echo] * 3)
    with pytest.raises(RuntimeError, match="invalid structured output"):
        provider.chat_json("context", RequirementExtraction)
    assert len(model.calls) == 3


def test_reject_schema_echo_allows_legitimate_payloads():
    """Real objects, including empty ones, must NOT be rejected."""
    _reject_schema_echo({"requirements": []}, RequirementExtraction)
    _reject_schema_echo({}, RequirementExtraction)
    _reject_schema_echo({"summary": "s", "procedures": []}, ProcedureExtraction)

    class HasTypeField(BaseModel):
        type: str = "small"
        id: str = "x"

    # A populated object for a model that genuinely owns a schema-like field
    # name is still valid and must pass.
    _reject_schema_echo({"type": "small", "id": "x"}, HasTypeField)


def test_chat_json_validates_nested_requirement():
    payload = {
        "requirements": [
            {
                "id": "req_1",
                "category": "policy",
                "text": "Follow the release policy",
                "relevant_tasks": ["task_1", "task_2"],
            }
        ]
    }
    provider, _ = _provider([json.dumps(payload)])
    result = provider.chat_json("context", RequirementExtraction)
    assert result.requirements[0].id == "req_1"
    assert result.requirements[0].category == "policy"


def test_chat_json_objective_analysis_populated():
    payload = {
        "objective": "Ship the product",
        "current_situation": "Kickoff",
        "success_criteria": ["GA available"],
        "constraints": ["Security review"],
        "stakeholders": ["Owner"],
        "decision_makers": ["Manager"],
        "external_dependencies": [],
        "timeline_flags": ["Deadline: 2026-12-01"],
        "priority_flags": ["Priority: high"],
        "notes": None,
    }
    provider, _ = _provider([json.dumps(payload)])
    result = provider.chat_json("context", ObjectiveAnalysis)
    assert result.objective == "Ship the product"
    assert result.success_criteria == ["GA available"]


def test_chat_content_blocks_text():
    model = FakeChatModel([])
    model.responses = [[{"type": "text", "text": "hello"}]]
    provider = LangChainStructuredProvider(model)
    assert provider.chat("ping") == "hello"


@pytest.mark.parametrize("model_cls", [ObjectiveAnalysis, ProcedureExtraction, RequirementExtraction])
def test_generated_example_validates_against_real_model(model_cls):
    """The prompt's example must be a genuinely valid instance of the schema."""
    node = _trim_schema(model_cls.model_json_schema())
    example = _example_value(node, node.get("$defs", {}))
    assert model_cls.model_validate(example) is not None


@pytest.mark.parametrize("model_cls", [ObjectiveAnalysis, ProcedureExtraction, RequirementExtraction])
def test_generated_example_has_no_schema_vocabulary(model_cls):
    """Example must show data only, never the schema the model echoes back."""
    node = _trim_schema(model_cls.model_json_schema())
    example = _example_value(node, node.get("$defs", {}))

    def collect_keys(value):
        keys = set()
        if isinstance(value, dict):
            keys |= set(value)
            for child in value.values():
                keys |= collect_keys(child)
        elif isinstance(value, list):
            for child in value:
                keys |= collect_keys(child)
        return keys

    # Structural schema vocabulary must never appear as an example key.
    # (Note: "description"/"required_information" are legitimate *field*
    # names in these models, so this checks exact keys, not substrings.)
    structural = {"$defs", "properties", "required", "title", "type", "items", "$ref", "anyOf"}
    assert not (collect_keys(example) & structural)


def test_trim_schema_keeps_field_named_description():
    """ProcedureOption.description is a required *field*, not schema noise."""
    node = _trim_schema(ProcedureExtraction.model_json_schema())
    fields = node["$defs"]["ProcedureOption"]["properties"]
    assert "description" in fields
    assert "command" in fields
    # Structural noise keys are still removed.
    assert "title" not in fields["command"]
    assert "default" not in node["properties"]["notes"]["items"]


def test_generated_example_populates_nested_objects():
    """Nested arrays must render real sub-objects, not empty placeholders."""
    node = _trim_schema(ProcedureExtraction.model_json_schema())
    example = _example_value(node, node.get("$defs", {}))
    step = example["procedures"][0]["steps"][0]
    assert step["options"] != [{}]
    assert step["options"][0]["description"] == "example"
    assert step["order"] == 1


def test_generated_example_uses_enum_values():
    node = _trim_schema(RequirementExtraction.model_json_schema())
    example = _example_value(node, node.get("$defs", {}))
    allowed = set(RequirementExtraction.model_fields["requirements"].annotation)
    assert example["requirements"][0]["category"] in {
        "policy", "process", "approval", "evidence", "definition"
    }


@pytest.mark.parametrize("model_cls", [ObjectiveAnalysis, ProcedureExtraction, RequirementExtraction])
def test_instruction_is_anti_echo_and_bounded(model_cls):
    instruction = _build_instruction(model_cls)
    assert "Return the POPULATED data" in instruction
    assert "Never output a schema" in instruction
    # Stripped schema noise must not be shipped on every call.
    # "title"/"default" are never field names in these models.
    assert '"title":' not in instruction
    assert '"default":' not in instruction
    # Keep the prompt small enough to stay fast; ~1.5k tokens ceiling.
    assert len(instruction) < 6000


SCHEMA_ECHO = json.dumps(
    {
        "$defs": {
            "Procedure": {
                "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
                "required": ["id", "name"],
                "type": "object",
            }
        },
        "properties": {"summary": {"type": "string"}, "procedures": {"type": "array"}},
        "required": ["summary"],
        "title": "ProcedureExtraction",
        "type": "object",
    }
)

GOOD_EXTRACTION = json.dumps(
    {"summary": "No indexed procedures apply.", "procedures": [], "notes": ["none"]}
)


def _nvidia_provider(captured):
    """A real ChatOpenAI pointed at a stubbed NVIDIA endpoint (no network)."""
    import httpx
    from langchain_openai import ChatOpenAI

    from app.llm.provider import MAX_OUTPUT_TOKENS

    def handler(request):
        body = json.loads(request.content.decode())
        captured.append(body)
        content = SCHEMA_ECHO if len(captured) == 1 else GOOD_EXTRACTION
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 0,
                "model": "meta/llama-3.2-11b-vision-instruct",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                },
            },
        )

    llm = ChatOpenAI(
        model="meta/llama-3.2-11b-vision-instruct",
        api_key="test-key-not-real",
        base_url="https://integrate.api.nvidia.com/v1",
        temperature=0,
        timeout=120,
        max_retries=0,
        extra_body={"max_tokens": MAX_OUTPUT_TOKENS},
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return LangChainStructuredProvider(llm)


def test_nvidia_payload_uses_standard_max_tokens():
    """NVIDIA rejects 'max_completion_tokens'; the cap must go out as max_tokens.

    langchain-openai 0.3.x rewrites a top-level ``max_tokens`` into
    ``max_completion_tokens``, so the cap is passed via ``extra_body``, which
    the OpenAI SDK merges verbatim into the request body.
    """
    captured = []
    provider = _nvidia_provider(captured)
    provider.extract_procedures(WorkRequest(goal="Prepare Project Alpha"))

    body = captured[0]
    assert body["max_tokens"] == MAX_OUTPUT_TOKENS
    assert "max_completion_tokens" not in body
    assert body["temperature"] == 0
    assert body["model"] == "meta/llama-3.2-11b-vision-instruct"
    # No credential may appear anywhere in the serialized request.
    assert "test-key-not-real" not in json.dumps(captured)


def test_end_to_end_recovers_from_schema_echo_with_corrective_retry():
    captured = []
    provider = _nvidia_provider(captured)
    result = provider.extract_procedures(WorkRequest(goal="Prepare Project Alpha"))

    assert result.summary == "No indexed procedures apply."
    assert result.procedures == []
    # One failed attempt (the echoed schema) plus one corrective retry.
    assert len(captured) == 2

    first_prompt = captured[0]["messages"][0]["content"]
    assert "Return the POPULATED data" in first_prompt
    assert "EXAMPLE of a valid POPULATED response" in first_prompt

    retry_prompt = captured[1]["messages"][0]["content"]
    assert "Your previous response was rejected" in retry_prompt
    assert "SchemaEchoError" in retry_prompt