from __future__ import annotations

import argparse
import json
import time

import httpx


SEED_NOTES = [
    {"id": 1, "title": "Tide table", "body": "Check the harbour window before departure."},
    {"id": 2, "title": "Repair kit", "body": "Pack tape, cord, and the small multitool."},
]
IMPORTED_BACKUP = {
    "schema_version": "1.0",
    "notes": [
        {"id": 7, "title": "Survey route", "body": "Begin at the eastern marker after sunrise."},
        {"id": 8, "title": "Waterproof case", "body": "Move the paper maps into the blue case."},
    ],
}


def wait_for_health(client: httpx.Client) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            response = client.get("/health")
            if response.status_code == 200 and response.json() == {"status": "ok"}:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError("Container did not become healthy within 30 seconds")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("expected", choices=["empty", "seed", "import", "imported"])
    arguments = parser.parse_args()

    with httpx.Client(base_url=arguments.base_url, timeout=10) as client:
        wait_for_health(client)
        if arguments.expected == "import":
            response = client.post(
                "/api/notes/import",
                files={
                    "backup": (
                        "notes-backup.json",
                        json.dumps(IMPORTED_BACKUP).encode("utf-8"),
                        "application/json",
                    )
                },
            )
            assert response.status_code == 200, response.text
            assert response.json() == {"status": "imported", "note_count": 2}
            exported = client.get("/api/notes/export")
            assert exported.status_code == 200
            assert exported.json() == IMPORTED_BACKUP
            invalid = client.post(
                "/api/notes/import",
                files={
                    "backup": (
                        "invalid.json",
                        b'{"schema_version":"2.0","notes":[]}',
                        "application/json",
                    )
                },
            )
            assert invalid.status_code == 400
            assert client.get("/api/notes").json() == IMPORTED_BACKUP["notes"]
            print("container_notes=imported_and_exported")
            print("invalid_import_preserved_notes=PASS")
            return

        expected_notes = {
            "empty": [],
            "seed": SEED_NOTES,
            "imported": IMPORTED_BACKUP["notes"],
        }[arguments.expected]
        response = client.get("/api/notes")
        assert response.status_code == 200
        assert response.json() == expected_notes, response.text
        print(f"container_notes={arguments.expected}")


if __name__ == "__main__":
    main()

