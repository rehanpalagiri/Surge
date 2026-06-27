import asyncio
import os
import time

import boto3
from botocore.config import Config
from services.telemetry import record_usage_event


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
    started = time.perf_counter()
    loop = asyncio.get_running_loop()
    try:
        client = _client()
        bucket = os.environ["R2_BUCKET_NAME"]
        resp = await loop.run_in_executor(None, lambda: client.get_object(Bucket=bucket, Key=key))
        body = await loop.run_in_executor(None, resp["Body"].read)
        await record_usage_event(
            operation="object_download", provider="cloudflare_r2", success=True,
            latency_ms=(time.perf_counter() - started) * 1000, output_bytes=len(body),
        )
        return body
    except Exception as exc:
        await record_usage_event(
            operation="object_download", provider="cloudflare_r2", success=False,
            latency_ms=(time.perf_counter() - started) * 1000,
            error_code=type(exc).__name__,
        )
        raise


async def object_size(key: str) -> int | None:
    started = time.perf_counter()
    loop = asyncio.get_running_loop()
    try:
        client = _client()
        bucket = os.environ["R2_BUCKET_NAME"]
        resp = await loop.run_in_executor(None, lambda: client.head_object(Bucket=bucket, Key=key))
        size = resp.get("ContentLength")
        await record_usage_event(
            operation="object_head", provider="cloudflare_r2", success=True,
            latency_ms=(time.perf_counter() - started) * 1000,
            output_bytes=0,
        )
        return int(size) if size is not None else None
    except Exception as exc:
        await record_usage_event(
            operation="object_head", provider="cloudflare_r2", success=False,
            latency_ms=(time.perf_counter() - started) * 1000,
            error_code=type(exc).__name__,
        )
        raise


async def delete(key: str) -> None:
    started = time.perf_counter()
    loop = asyncio.get_running_loop()
    try:
        client = _client()
        bucket = os.environ["R2_BUCKET_NAME"]
        await loop.run_in_executor(None, lambda: client.delete_object(Bucket=bucket, Key=key))
        await record_usage_event(
            operation="object_delete", provider="cloudflare_r2", success=True,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
    except Exception as exc:
        await record_usage_event(
            operation="object_delete", provider="cloudflare_r2", success=False,
            latency_ms=(time.perf_counter() - started) * 1000,
            error_code=type(exc).__name__,
        )
        raise
