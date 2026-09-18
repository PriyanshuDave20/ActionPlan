from pydantic import BaseModel, Field


class Evidence(BaseModel):
    content: str
    source: str | None = None
    page: int | None = None
    document_type: str | None = Field(default=None, alias="doc_type")

    model_config = {"populate_by_name": True}