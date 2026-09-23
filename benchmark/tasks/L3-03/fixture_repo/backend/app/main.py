from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict


FRONTEND_ORIGIN = "http://127.0.0.1:8080"


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str


def create_app() -> FastAPI:
    application = FastAPI(title="Northstar Account Recovery API")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[FRONTEND_ORIGIN],
        allow_credentials=False,
        allow_methods=["POST"],
        allow_headers=["Content-Type"],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/v2/auth/password-reset", status_code=status.HTTP_202_ACCEPTED)
    def request_password_reset(payload: PasswordResetRequest) -> dict[str, str]:
        email = payload.email.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise HTTPException(status_code=422, detail="Enter a valid email address")
        return {"status": "accepted", "email": email, "request_id": "RST-2048"}

    return application


app = create_app()

