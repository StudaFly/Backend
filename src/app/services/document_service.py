from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.schemas.document import DocumentRead


async def list_documents(db: AsyncSession, user_id: UUID, mobility_id: UUID) -> list[DocumentRead]:
    # TODO: fetch documents for mobility, verify ownership
    raise NotImplementedError


async def upload_document(
    db: AsyncSession,
    user_id: UUID,
    mobility_id: UUID,
    file_bytes: bytes,
    filename: str,
    category: str | None,
) -> DocumentRead:
    # TODO: upload to S3 via storage_service, save record to DB
    raise NotImplementedError


async def get_document(db: AsyncSession, user_id: UUID, document_id: UUID) -> DocumentRead:
    # TODO: fetch document, verify ownership, return with signed S3 URL
    raise NotImplementedError


async def delete_document(db: AsyncSession, user_id: UUID, document_id: UUID) -> None:
    # TODO: delete from S3 and DB, verify ownership
    raise NotImplementedError
