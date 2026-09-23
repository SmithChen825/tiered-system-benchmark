from datetime import date

from pydantic import BaseModel, Field, field_validator


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    due_date: date

    @field_validator("due_date", mode="before")
    @classmethod
    def require_due_date(cls, value: object) -> object:
        """Reject missing form values before Pydantic performs date parsing."""
        if value is None or value == "":
            raise ValueError("due_date is required")
        return value


class TaskRead(BaseModel):
    id: int
    title: str
    description: str
    due_date: date | None
