from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

from fastapi.testclient import TestClient
import pytest


REPOSITORY = Path(os.environ["L2_03_REPO"]).resolve()
AUTHORITATIVE_STORE = REPOSITORY / "storage" / "notes.json"
WRONG_CWD_STORE = REPOSITORY / "app" / "storage"
SEED_NOTES = [
    {
        "id": 1,
        "title": "Tide table",
        "body": "Check the harbour window before departure.",
    },
    {
        "id": 2,
        "title": "Repair kit",
        "body": "Pack tape, cord, and the small multitool.",
    },
]
IMPORTED_BACKUP = {
    "schema_version": "1.0",
    "notes": [
        {
            "id": 7,
            "title": "Survey route",
            "body": "Begin at the eastern marker after sunrise.",
        },
        {
            "id": 8,
            "title": "Waterproof case",
            "body": "Move the paper maps into the blue case.",
        },
    ],
}


@pytest.fixture(autouse=True)
def restore_fixture_storage():
    original = AUTHORITATIVE_STORE.read_bytes()
    shutil.rmtree(WRONG_CWD_STORE, ignore_errors=True)
    yield
    AUTHORITATIVE_STORE.write_bytes(original)
    shutil.rmtree(WRONG_CWD_STORE, ignore_errors=True)


def load_application(working_directory: Path):
    previous = Path.cwd()
    try:
        os.chdir(working_directory)
        module_path = REPOSITORY / "app" / "main.py"
        name = f"l2_03_candidate_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(name, module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        os.chdir(previous)


def upload(client: TestClient, payload: dict) -> object:
    return client.post(
        "/api/notes/import",
        files={
            "backup": (
                "notes-backup.json",
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )
        },
    )


def test_seed_notes_load_from_authoritative_project_store():
    module = load_application(REPOSITORY / "app")
    response = TestClient(module.app).get("/api/notes")
    assert response.status_code == 200
    assert response.json() == SEED_NOTES


def test_import_and_export_update_the_authoritative_project_store():
    module = load_application(REPOSITORY / "app")
    client = TestClient(module.app)
    imported = upload(client, IMPORTED_BACKUP)
    exported = client.get("/api/notes/export")
    physical = json.loads(AUTHORITATIVE_STORE.read_text(encoding="utf-8"))
    assert imported.status_code == 200
    assert imported.json() == {"status": "imported", "note_count": 2}
    assert exported.status_code == 200
    assert exported.headers["content-disposition"] == 'attachment; filename="notes-backup.json"'
    assert exported.json() == IMPORTED_BACKUP
    assert physical == IMPORTED_BACKUP


def test_import_survives_restart_from_a_different_working_directory():
    first_module = load_application(REPOSITORY / "app")
    assert upload(TestClient(first_module.app), IMPORTED_BACKUP).status_code == 200
    restarted_module = load_application(REPOSITORY)
    response = TestClient(restarted_module.app).get("/api/notes")
    assert response.status_code == 200
    assert response.json() == IMPORTED_BACKUP["notes"]


def test_invalid_backup_is_rejected_without_changing_saved_notes():
    before = AUTHORITATIVE_STORE.read_bytes()
    module = load_application(REPOSITORY / "app")
    client = TestClient(module.create_app(AUTHORITATIVE_STORE))
    invalid = {"schema_version": "2.0", "notes": []}
    response = upload(client, invalid)
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid notes backup"}
    assert AUTHORITATIVE_STORE.read_bytes() == before


def test_default_storage_path_is_anchored_to_the_project_root():
    module = load_application(REPOSITORY / "app")
    assert module.PROJECT_ROOT == REPOSITORY
    assert module.STORAGE_PATH == AUTHORITATIVE_STORE


def test_backup_schema_and_route_contract_are_preserved():
    source = (REPOSITORY / "app" / "main.py").read_text(encoding="utf-8")
    assert 'schema_version: str' in source
    assert 'notes: list[Note]' in source
    assert 'id: int' in source and 'title: str' in source and 'body: str' in source
    assert '@application.get("/api/notes")' in source
    assert '@application.get("/api/notes/export")' in source
    assert '@application.post("/api/notes/import")' in source
    assert "temporary.replace(path)" in source


def test_health_and_single_service_volume_architecture_are_preserved():
    module = load_application(REPOSITORY / "app")
    client = TestClient(module.create_app(AUTHORITATIVE_STORE))
    assert client.get("/health").json() == {"status": "ok"}
    compose = (REPOSITORY / "compose.yaml").read_text(encoding="utf-8")
    service_section = compose.split("volumes:", 1)[0]
    assert service_section.count("  app:") == 1
    assert "note_data:/workspace/storage" in compose
    assert compose.count("build:") == 1
    dockerfile = (REPOSITORY / "Dockerfile").read_text(encoding="utf-8")
    assert "WORKDIR /workspace/app" in dockerfile
    assert 'VOLUME ["/workspace/storage"]' in dockerfile
