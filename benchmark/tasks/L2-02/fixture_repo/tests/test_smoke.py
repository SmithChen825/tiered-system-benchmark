from fastapi.testclient import TestClient

from app.main import create_app


def test_home_page_contains_task_form(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_DB_PATH", str(tmp_path / "tasks.db"))
    with TestClient(create_app()) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'action="/tasks"' in response.text
    assert 'name="due_date"' in response.text


def test_task_with_supplied_date_can_be_created(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_DB_PATH", str(tmp_path / "tasks.db"))
    with TestClient(create_app()) as client:
        response = client.post(
            "/tasks",
            data={
                "title": "Prepare demo",
                "description": "Verify the normal dated path",
                "due_date": "2030-01-15",
            },
        )

    assert response.status_code == 201
    assert response.json()["due_date"] == "2030-01-15"
