import json
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import quote

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("practice9")
S3_BUCKET = os.getenv("S3_BUCKET", "data-lake-bucket")
s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["S3_ENDPOINT"],
    aws_access_key_id=os.environ["S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    region_name="us-east-1",
    config=Config(
        s3={"addressing_style": "path"},
        connect_timeout=5, read_timeout=30,
        retries={"mode": "standard", "max_attempts": 3},
        max_pool_connections=8,
    ),
)
MIB = 1024 * 1024
TRANSFER = TransferConfig(
    multipart_threshold=5 * MIB,
    multipart_chunksize=5 * MIB,
    max_concurrency=4,
    use_threads=True,
)


def record_multipart(model, **kwargs):
    if model.name in {"CreateMultipartUpload", "UploadPart", "CompleteMultipartUpload"}:
        logger.info("S3 multipart operation=%s", model.name)


s3.meta.events.register("before-call.s3", record_multipart)


@asynccontextmanager
async def lifespan(app):
    # Compose запускает приложение только после успешной инициализации бакета.
    s3.head_bucket(Bucket=S3_BUCKET)
    logger.info("S3 bucket ready: %s", S3_BUCKET)
    yield
    s3.close()


app = FastAPI(title="S3 Data Lake Service", lifespan=lifespan)


class S3Object(BaseModel):
    key: str
    size: int
    last_modified: str


def s3_error(error):
    if isinstance(error, ClientError):
        code = error.response["Error"]["Code"]
        if code in {"NoSuchKey", "404"}:
            return HTTPException(status_code=404, detail="Object not found")
    logger.error("S3 operation failed: %s", type(error).__name__)
    return HTTPException(status_code=503, detail="Object storage is unavailable")


def validate_key(key):
    if not key or len(key.encode("utf-8")) > 1024:
        raise HTTPException(status_code=422, detail="Key must contain 1–1024 UTF-8 bytes")
    return key


def objects(prefix=""):
    # Пагинация: обычный list_objects_v2 возвращает максимум 1000 объектов.
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        yield from page.get("Contents", [])


def read_bytes(key):
    result = s3.get_object(Bucket=S3_BUCKET, Key=validate_key(key))
    body = result["Body"]
    try:
        return body.read()
    finally:
        body.close()


@app.get("/")
def root():
    return {"message": "S3 Data Lake Service is running!"}


@app.get("/health")
def health():
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
    except (ClientError, BotoCoreError) as error:
        raise s3_error(error)
    return {"status": "healthy", "bucket": S3_BUCKET}


@app.get("/buckets/")
def list_buckets():
    try:
        return {"buckets": [b["Name"] for b in s3.list_buckets()["Buckets"]]}
    except (ClientError, BotoCoreError) as error:
        raise s3_error(error)


@app.get("/objects/")
def list_objects(prefix: str = "", file_type: str | None = Query(None, pattern=r"^\.?[A-Za-z0-9]+$")):
    extension = "." + file_type.lstrip(".").lower() if file_type else None
    try:
        result = [
            S3Object(key=o["Key"], size=o["Size"], last_modified=o["LastModified"].isoformat())
            for o in objects(prefix)
            if extension is None or o["Key"].lower().endswith(extension)
        ]
    except (ClientError, BotoCoreError) as error:
        raise s3_error(error)
    return {"objects": result, "count": len(result)}


@app.get("/objects/{key:path}")
def get_object(key: str):
    try:
        content = read_bytes(key).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail="Binary object: use /download/{key}")
    except (ClientError, BotoCoreError) as error:
        raise s3_error(error)
    try:
        return {"key": key, "data": json.loads(content), "content_type": "json"}
    except json.JSONDecodeError:
        return {"key": key, "data": content, "content_type": "text"}


@app.post("/upload/")
def upload_object(key: str = Query(min_length=1), content: str = Query()):
    try:
        s3.put_object(Bucket=S3_BUCKET, Key=validate_key(key), Body=content.encode("utf-8"))
    except (ClientError, BotoCoreError) as error:
        raise s3_error(error)
    return {"message": f"Object '{key}' uploaded successfully"}


@app.get("/aggregate/")
def aggregate_data():
    results = []
    try:
        for obj in objects():
            key = obj["Key"]
            if key.lower().endswith(".json"):
                try:
                    results.append({"file": key, "data": json.loads(read_bytes(key))})
                except (json.JSONDecodeError, UnicodeDecodeError):
                    results.append({"file": key, "error": "Invalid JSON"})
    except (ClientError, BotoCoreError) as error:
        raise s3_error(error)
    return {"files_processed": len(results), "data": results}


@app.get("/download/{key:path}")
def download_object(key: str):
    try:
        result = s3.get_object(Bucket=S3_BUCKET, Key=validate_key(key))
    except (ClientError, BotoCoreError) as error:
        raise s3_error(error)
    body = result["Body"]

    def chunks():
        try:
            yield from body.iter_chunks(chunk_size=64 * 1024)
        finally:
            body.close()

    # filename* сохраняет UTF-8, а quote исключает внедрение заголовков через имя.
    filename = key.rsplit("/", 1)[-1] or "download"
    return StreamingResponse(
        chunks(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
            "Content-Length": str(result["ContentLength"]),
        },
    )


@app.post("/upload-file/")
def upload_file(file: UploadFile = File(...), key: str | None = Query(None)):
    target = validate_key(key if key is not None else (file.filename or "upload.bin"))
    try:
        # UploadFile хранит большой файл во временном файле, а не целиком в памяти.
        # boto3 делит его на части по 5 МиБ и передаёт до 4 частей одновременно.
        s3.upload_fileobj(
            file.file, S3_BUCKET, target,
            ExtraArgs={"ContentType": "application/octet-stream"},
            Config=TRANSFER,
        )
        meta = s3.head_object(Bucket=S3_BUCKET, Key=target)
    except (ClientError, BotoCoreError) as error:
        raise s3_error(error)
    logger.info("File uploaded key=%s bytes=%s etag=%s", target, meta["ContentLength"], meta["ETag"])
    return {"key": target, "size": meta["ContentLength"], "etag": meta["ETag"].strip('"')}
