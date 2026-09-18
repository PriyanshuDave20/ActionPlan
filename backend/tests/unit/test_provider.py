import pytest

from app.llm.provider import MockLLMProvider
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