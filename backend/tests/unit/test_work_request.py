from datetime import date

from pydantic import ValidationError

from app.models.work_request import Person, WorkRequest, WorkRequestInput, compile_work_request


def test_empty_goal_rejected():
    try:
        WorkRequestInput(goal="")
    except ValidationError:
        return
    raise AssertionError("empty goal should be rejected")


def test_people_and_roles_compiled():
    payload = WorkRequestInput(
        goal="Move the office",
        people_involved=[
            Person(name="Ada", role="facilities"),
            Person(name="Lin", role="manager"),
        ],
    )
    compiled = compile_work_request(payload)
    assert compiled.people == payload.people_involved
    assert compiled.roles == ["facilities", "manager"]


def test_work_request_defaults():
    compiled = compile_work_request(WorkRequestInput(goal="Ship the release"))
    assert compiled.priority == "medium"
    assert compiled.deadline is None
    assert compiled.constraints == []
    assert compiled.resources == []
    assert compiled.success_criteria == []


def test_deadline_accepted_as_iso_date():
    request = WorkRequest(goal="Plan the Q3 review", deadline=date(2026, 9, 30))
    assert request.deadline == date(2026, 9, 30)