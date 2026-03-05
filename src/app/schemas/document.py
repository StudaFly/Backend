import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentRead(BaseModel):
    id: uuid.UUID
    mobility_id: uuid.UUID
    file_url: str
    category: str | None
    uploaded_at: datetime

    model_config = {"from_attributes": True}
