import uuid

from pydantic import BaseModel


class DestinationCreate(BaseModel):
    country: str
    city: str


class DestinationRead(BaseModel):
    id: uuid.UUID
    country: str
    city: str

    model_config = {"from_attributes": True}
