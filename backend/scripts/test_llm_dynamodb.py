"""Smoke test for the NVIDIA LLM provider and DynamoDB persistence.

This script verifies two things:

1. The configured NVIDIA-hosted LLM can successfully process a goal.
2. The resulting workflow can be persisted to DynamoDB.

This test intentionally refuses to run with the mock provider.
"""

import argparse
import sys
from uuid import uuid4

from app.config import get_settings
from app.llm.provider import create_llm_provider
from app.memory.dynamodb import DynamoDBMemoryStore
from app.models.goal import GoalInput
from app.models.workflow import WorkflowState


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Test the NVIDIA LLM and save the resulting workflow "
            "to DynamoDB."
        )
    )

    parser.add_argument(
        "goal",
        nargs="?",
        help=(
            "Workplace goal to send to the LLM. "
            "If omitted, you will be prompted."
        ),
    )

    return parser.parse_args()


def get_goal(value: str | None) -> str:
    """Get and validate the workplace goal."""

    goal = (
        value
        if value is not None
        else input("Enter a workplace goal: ")
    )

    return GoalInput(goal=goal).goal


def validate_nvidia_settings(settings) -> None:
    """Validate that the application is configured for NVIDIA."""

    provider = settings.llm_provider.lower().strip()

    if provider == "mock":
        raise ValueError(
            "Refusing to run: LLM_PROVIDER=mock. "
            "Set LLM_PROVIDER=nvidia in your .env file."
        )

    if provider != "nvidia":
        raise ValueError(
            f"This smoke test requires LLM_PROVIDER=nvidia, "
            f"but the current provider is '{provider}'."
        )

    missing = []

    if not settings.resolved_llm_api_key:
        missing.append("LLM_API_KEY")

    if not settings.resolved_llm_model:
        missing.append("LLM_MODEL")

    if not settings.resolved_llm_base_url:
        missing.append("LLM_BASE_URL")

    if missing:
        raise ValueError(
            "Missing NVIDIA LLM configuration: "
            + ", ".join(missing)
        )


def main() -> int:
    args = parse_args()

    try:
        # ---------------------------------------------------------
        # 1. Load configuration
        # ---------------------------------------------------------
        settings = get_settings()

        validate_nvidia_settings(settings)

        goal = get_goal(args.goal)

        print()
        print("=" * 60)
        print("NVIDIA LLM + DynamoDB Smoke Test")
        print("=" * 60)

        print(f"Provider:       {settings.llm_provider}")
        print(f"Model:          {settings.resolved_llm_model}")
        print(f"Base URL:       {settings.resolved_llm_base_url}")
        print(
            f"API key set:    "
            f"{bool(settings.resolved_llm_api_key)}"
        )
        print(f"Goal:           {goal}")
        print("=" * 60)
        print()

        # ---------------------------------------------------------
        # 2. Create the actual application LLM provider
        # ---------------------------------------------------------
        print("Creating NVIDIA LLM provider...", flush=True)

        provider = create_llm_provider(settings)

        print(
            "Provider created successfully.",
            flush=True,
        )

        # ---------------------------------------------------------
        # 3. Call the actual NVIDIA-hosted DeepSeek model
        # ---------------------------------------------------------
        print(
            "Sending request to NVIDIA / DeepSeek V4 Pro...",
            flush=True,
        )

        response = provider.chat(goal)

        if not response:
            raise RuntimeError(
                "The LLM returned an empty response."
            )

        print()
        print("=" * 60)
        print("LLM CALL SUCCESSFUL")
        print("=" * 60)
        print(response)
        print("=" * 60)
        print()

        # ---------------------------------------------------------
        # 4. Create workflow state
        # ---------------------------------------------------------
        workflow_id = str(uuid4())

        workflow = WorkflowState(
            workflow_id=workflow_id,
            original_goal=goal,
            execution_metadata={
                "source": "scripts/test_llm_dynamodb.py",
                "llm_provider": settings.llm_provider,
                "llm_model": settings.resolved_llm_model,
                "chat_response": response,
            },
        )

        print(
            f"Created workflow state: {workflow_id}",
            flush=True,
        )

        # ---------------------------------------------------------
        # 5. Save workflow to DynamoDB
        # ---------------------------------------------------------
        print(
            "Saving workflow to DynamoDB...",
            flush=True,
        )

        memory_store = DynamoDBMemoryStore(settings)

        memory_store.save_workflow(workflow)

        print()
        print("=" * 60)
        print("DYNAMODB SAVE SUCCESSFUL")
        print("=" * 60)
        print(
            f"Workflow ID:    {workflow_id}"
        )
        print(
            f"DynamoDB table: {settings.dynamodb_table_name}"
        )
        print("=" * 60)
        print()

        print("ALL TESTS PASSED.")
        print()
        print("1. NVIDIA LLM call: SUCCESS")
        print("2. DynamoDB persistence: SUCCESS")

        return 0

    except (KeyboardInterrupt, EOFError):
        print(
            "\nInput cancelled.",
            file=sys.stderr,
        )
        return 130

    except Exception as error:
        print()
        print("=" * 60)
        print("TEST FAILED")
        print("=" * 60)
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        print("=" * 60)

        return 1


if __name__ == "__main__":
    raise SystemExit(main())

