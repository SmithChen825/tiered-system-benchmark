from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_session
from .models import User
from .schemas import UserRead


FRONTEND_ORIGIN = "http://127.0.0.1:8080"


def create_app() -> FastAPI:
    application = FastAPI(title="User Directory API")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/users", response_model=list[UserRead])
    def users(session: Session = Depends(get_session)) -> list[User]:
        return list(session.scalars(select(User).order_by(User.id)))

    return application


app = create_app()
