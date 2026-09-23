from datetime import date

from pydantic import BaseModel, Field, field_validator


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    due_date: date | None = None

    @field_validator("due_date", mode="before")
    @classmethod
    def normalize_empty_due_date(cls, value: object) -> object:
        """Treat an omitted or empty form value as no due date."""
        if value is None or value == "":
            return None
        return value


class TaskRead(BaseModel):
    id: int
    title: str
    description: str
    due_date: date | None
