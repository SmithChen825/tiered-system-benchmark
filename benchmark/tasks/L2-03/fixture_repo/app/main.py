from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_PATH = Path(os.getenv("NOTE_STORAGE_PATH", "storage/notes.json")).expanduser().resolve()


class Note(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    title: str
    body: str


class Backup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    notes: list[Note]


def read_backup(path: Path) -> Backup:
    if not path.exists():
        return Backup(schema_version="1.0", notes=[])
    try:
        backup = Backup.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise RuntimeError(f"Saved notes are invalid: {error}") from error
    if backup.schema_version != "1.0":
        raise RuntimeError("Saved notes use an unsupported schema version")
    return backup


def write_backup(path: Path, backup: Backup) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(backup.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def create_app(storage_path: Path | None = None) -> FastAPI:
    application = FastAPI(title="Fieldnote Archive")
    store = (storage_path or STORAGE_PATH).resolve()

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/", response_class=HTMLResponse)
    def index() -> str:
        return "<!doctype html><title>Fieldnote Archive</title><main><h1>Saved notes</h1><p>Use the JSON import and export endpoints to manage backups.</p></main>"

    @application.get("/api/notes")
    def list_notes() -> list[dict[str, Any]]:
        return [note.model_dump() for note in read_backup(store).notes]

    @application.get("/api/notes/export")
    def export_notes() -> JSONResponse:
        payload = read_backup(store).model_dump()
        return JSONResponse(
            payload,
            headers={"Content-Disposition": 'attachment; filename="notes-backup.json"'},
        )

    @application.post("/api/notes/import")
    async def import_notes(backup: UploadFile = File(...)) -> dict[str, int | str]:
        try:
            raw = await backup.read()
            payload = Backup.model_validate_json(raw)
            if payload.schema_version != "1.0":
                raise ValueError("unsupported schema version")
            ids = [note.id for note in payload.notes]
            if len(ids) != len(set(ids)):
                raise ValueError("note IDs must be unique")
        except (ValidationError, ValueError, UnicodeDecodeError) as error:
            raise HTTPException(status_code=400, detail="Invalid notes backup") from error
        write_backup(store, payload)
        return {"status": "imported", "note_count": len(payload.notes)}

    return application


app = create_app()

