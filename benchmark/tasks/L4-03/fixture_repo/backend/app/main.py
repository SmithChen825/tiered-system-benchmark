from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .database import engine


FRONTEND_ORIGIN = "http://127.0.0.1:8080"


@asynccontextmanager
async def lifespan(_: FastAPI):
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="Northstar Operations API", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[FRONTEND_ORIGIN],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}

    @application.get("/api/dashboard")
    def dashboard() -> dict[str, object]:
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT name, value FROM dashboard_metrics ORDER BY display_order")
            ).mappings()
            metrics = [{"name": row["name"], "value": row["value"]} for row in rows]
        return {"status": "operational", "database": "reachable", "metrics": metrics}

    return application


app = create_app()

