from src.app.core.config import settings


def get_s3_client():
    import boto3

    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )


async def upload_file(
    file_bytes: bytes, key: str, content_type: str = "application/octet-stream"
) -> str:
    # TODO: upload to S3, return public or signed URL
    raise NotImplementedError


async def delete_file(key: str) -> None:
    # TODO: delete object from S3
    raise NotImplementedError


async def get_signed_url(key: str, expires_in: int = 3600) -> str:
    # TODO: generate pre-signed S3 URL
    raise NotImplementedError
