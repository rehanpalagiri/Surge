import asyncio
import os

import boto3
from botocore.config import Config


def _client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def presigned_upload_url(key: str, content_type: str, expires: int = 300) -> str:
    bucket = os.environ["R2_BUCKET_NAME"]
    return _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )


async def download(key: str) -> bytes:
    loop = asyncio.get_running_loop()
    client = _client()
    bucket = os.environ["R2_BUCKET_NAME"]
    resp = await loop.run_in_executor(None, lambda: client.get_object(Bucket=bucket, Key=key))
    return await loop.run_in_executor(None, resp["Body"].read)


async def delete(key: str) -> None:
    loop = asyncio.get_running_loop()
    client = _client()
    bucket = os.environ["R2_BUCKET_NAME"]
    await loop.run_in_executor(None, lambda: client.delete_object(Bucket=bucket, Key=key))
