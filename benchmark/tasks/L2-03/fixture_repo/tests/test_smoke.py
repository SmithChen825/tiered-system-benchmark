from pathlib import Path


def test_notes_backup_fixture_is_present():
    root = Path(__file__).resolve().parents[1]
    assert (root / "app" / "main.py").is_file()
    assert (root / "storage" / "notes.json").is_file()
    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    assert "note_data:/workspace/storage" in compose

