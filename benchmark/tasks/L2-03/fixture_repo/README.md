# Fieldnote Archive

Single-service FastAPI notes application. Run with `docker compose up --build`; the service is available at `http://127.0.0.1:8000`. The JSON backup format is `{"schema_version":"1.0","notes":[{"id":1,"title":"...","body":"..."}]}`. Import uses multipart field `backup` at `POST /api/notes/import`; export is available at `GET /api/notes/export`.

