from fastapi import APIRouter

router = APIRouter()


@router.get("/mobilities/{mobility_id}/documents")
async def list_documents(mobility_id: str):
    # TODO: return documents via document_service.list_documents()
    raise NotImplementedError


@router.post("/mobilities/{mobility_id}/documents", status_code=201)
async def upload_document(mobility_id: str):
    # TODO: upload document via document_service.upload_document()
    raise NotImplementedError


@router.get("/documents/{document_id}")
async def get_document(document_id: str):
    # TODO: return document via document_service.get_document()
    raise NotImplementedError


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str):
    # TODO: delete document via document_service.delete_document()
    raise NotImplementedError
