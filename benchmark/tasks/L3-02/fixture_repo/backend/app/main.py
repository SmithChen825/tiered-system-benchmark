from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

FRONTEND_ORIGIN = "http://127.0.0.1:8080"
ORDER = {"id": "ORD-2048", "customer": "Maya Chen", "order_status": "Ready for dispatch", "updated_at": "2026-08-28T09:30:00Z"}

def create_app() -> FastAPI:
    application = FastAPI(title="Order Status API")
    application.add_middleware(CORSMiddleware, allow_origins=[FRONTEND_ORIGIN], allow_credentials=True, allow_methods=["GET"], allow_headers=["Content-Type"])
    @application.get("/health")
    def health() -> dict[str, str]: return {"status": "ok"}
    @application.get("/api/orders/{order_id}")
    def order(order_id: str) -> dict[str, str]:
        return ORDER if order_id == ORDER["id"] else {"id": order_id, "customer": "Unknown", "order_status": "Not found", "updated_at": ORDER["updated_at"]}
    return application

app = create_app()
