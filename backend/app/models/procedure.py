from pydantic import BaseModel, Field


class ProcedureOption(BaseModel):
    command: str
    description: str
    flags: list[str] = Field(default_factory=list)


class ProcedureStep(BaseModel):
    order: int = Field(ge=1)
    action: str
    required_information: list[str] = Field(default_factory=list)
    optional: bool = False
    options: list[ProcedureOption] = Field(default_factory=list)


class Procedure(BaseModel):
    id: str
    name: str
    source: str | None = None
    summary: str | None = None
    steps: list[ProcedureStep] = Field(default_factory=list)