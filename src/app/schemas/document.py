import uuid
from datetime import datetime

from src.app.schemas.common import StudaFlyBaseModel


class DocumentRead(StudaFlyBaseModel):
    id: uuid.UUID
    mobility_id: uuid.UUID
    file_url: str
    category: str | None
    uploaded_at: datetime
