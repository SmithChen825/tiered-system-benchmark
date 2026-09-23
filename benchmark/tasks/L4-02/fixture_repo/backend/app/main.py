from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_session
from .models import Customer
from .schemas import CustomerCreate, CustomerRead

FRONTEND_ORIGIN = "http://127.0.0.1:8080"

def create_app() -> FastAPI:
    application = FastAPI(title="Customer Directory API")
    application.add_middleware(CORSMiddleware, allow_origins=[FRONTEND_ORIGIN], allow_credentials=True, allow_methods=["GET","POST"], allow_headers=["Content-Type"])
    @application.get("/health")
    def health() -> dict[str,str]: return {"status":"ok"}
    @application.get("/api/customers", response_model=list[CustomerRead])
    def customers(session: Session = Depends(get_session)) -> list[Customer]: return list(session.scalars(select(Customer).order_by(Customer.id)))
    @application.post("/api/customers", response_model=CustomerRead, status_code=201)
    def create_customer(payload: CustomerCreate, session: Session = Depends(get_session)) -> Customer:
        customer = Customer(name=payload.name, email=payload.email)
        session.add(customer); session.commit(); session.refresh(customer); return customer
    return application

app = create_app()
