import os
import re
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPOSITORY = Path(os.environ["L2_02_REPO"]).resolve()
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from app.main import create_app  # noqa: E402


@pytest.fixture
def db_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "tasks.db"
    monkeypatch.setenv("TASK_DB_PATH", str(path))
    return path


def test_omitted_due_date_is_accepted_and_persisted_as_null(db_path):
    with TestClient(create_app()) as client:
        response = client.post(
            "/tasks",
            data={"title": "Write methodology", "description": "Draft section 4"},
        )

    assert response.status_code == 201
    assert response.json()["due_date"] is None
    assert _stored_due_date(db_path, response.json()["id"]) is None


def test_empty_due_date_is_accepted_and_persisted_as_null(db_path):
    with TestClient(create_app()) as client:
        response = client.post(
            "/tasks",
            data={"title": "Run pilot", "description": "", "due_date": ""},
        )

    assert response.status_code == 201
    assert response.json()["due_date"] is None
    assert _stored_due_date(db_path, response.json()["id"]) is None


def test_valid_iso_date_is_preserved(db_path):
    with TestClient(create_app()) as client:
        response = client.post(
            "/tasks",
            data={"title": "Submit thesis", "due_date": "2030-11-02"},
        )

    assert response.status_code == 201
    assert response.json()["due_date"] == "2030-11-02"
    assert _stored_due_date(db_path, response.json()["id"]) == "2030-11-02"


def test_malformed_supplied_date_remains_invalid(db_path):
    with TestClient(create_app()) as client:
        response = client.post(
            "/tasks",
            data={"title": "Invalid date example", "due_date": "02/11/2030"},
        )

    assert response.status_code == 422


def test_title_remains_required(db_path):
    with TestClient(create_app()) as client:
        response = client.post(
            "/tasks",
            data={"title": "", "description": "No title", "due_date": ""},
        )

    assert response.status_code == 422


def test_created_task_survives_application_restart(db_path):
    with TestClient(create_app()) as first_client:
        created = first_client.post(
            "/tasks",
            data={"title": "Persistent task", "due_date": ""},
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

    with TestClient(create_app()) as second_client:
        retrieved = second_client.get(f"/tasks/{task_id}")

    assert retrieved.status_code == 200
    assert retrieved.json() == {
        "id": task_id,
        "title": "Persistent task",
        "description": "",
        "due_date": None,
    }


def test_form_does_not_require_due_date_in_browser_markup(db_path):
    with TestClient(create_app()) as client:
        response = client.get("/")

    assert response.status_code == 200
    due_date_control = response.text.split('name="due_date"', maxsplit=1)[0].rsplit(
        "<input", maxsplit=1
    )[1]
    assert "required" not in due_date_control


def test_repair_does_not_hard_code_evaluator_examples_or_replacement_date():
    application_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((REPOSITORY / "app").rglob("*"))
        if path.is_file() and path.suffix in {".py", ".html", ".js"}
    )
    evaluator_examples = {
        "Write methodology",
        "Run pilot",
        "Submit thesis",
        "Persistent task",
        "2030-11-02",
        "02/11/2030",
    }
    assert not any(example in application_sources for example in evaluator_examples)
    assert not re.search(r"\b20\d{2}-\d{2}-\d{2}\b", application_sources)


def _stored_due_date(db_path: Path, task_id: int) -> str | None:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT due_date FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    assert row is not None
    return row[0]
