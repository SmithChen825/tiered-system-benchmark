from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


ALLOWED_ORIGINS = ["http://127.0.0.1:5173"]


def create_app() -> FastAPI:
    application = FastAPI(title="Account API")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/account")
    def account() -> dict[str, object]:
        return {
            "id": 1042,
            "name": "Ada Lovelace",
            "role": "Platform Engineer",
            "plan": "Research",
            "active": True,
        }

    return application


app = create_app()
