import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from .schemas import TaskCreate


def database_path() -> Path:
    configured = os.environ.get("TASK_DB_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "data" / "tasks.db"


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                due_date TEXT NULL
            )
            """
        )


def create_task(task: TaskCreate) -> dict[str, Any]:
    stored_due_date = _serialize_date(task.due_date)
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO tasks (title, description, due_date) VALUES (?, ?, ?)",
            (task.title, task.description, stored_due_date),
        )
        task_id = int(cursor.lastrowid)
        row = connection.execute(
            "SELECT id, title, description, due_date FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def get_task(task_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT id, title, description, due_date FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def list_tasks() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, title, description, due_date FROM tasks ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def _serialize_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None
