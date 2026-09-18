from pydantic import BaseModel, Field


class GoalInput(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)