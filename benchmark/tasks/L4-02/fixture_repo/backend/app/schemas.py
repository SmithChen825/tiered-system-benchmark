from pydantic import BaseModel, ConfigDict

class CustomerCreate(BaseModel):
    name: str
    email: str

class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
