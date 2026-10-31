import json
import logging
import os
import socket
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from typing import Annotated

import psycopg2
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from redis import Redis, RedisError

LOG_DIR = os.getenv("LOG_DIR", "/var/log/fastapi")
os.makedirs(LOG_DIR, exist_ok=True)
logger = logging.getLogger("practice6")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
# У каждой реплики свой файл: ротация общего файла из нескольких процессов небезопасна.
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, f"app-{socket.gethostname()}.log"),
    maxBytes=1_000_000, backupCount=3,
)
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

cache = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
CACHE_KEY = "items:all"
CACHE_TTL = 30


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "db"),
        dbname=os.getenv("DB_NAME", "fastapi_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
    )


@asynccontextmanager
async def lifespan(app):
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                price DOUBLE PRECISION NOT NULL CHECK (price >= 0)
            )""")
    finally:
        conn.close()
    logger.info("Application started instance=%s", socket.gethostname())
    yield
    logger.info("Application stopped instance=%s", socket.gethostname())
    cache.close()


app = FastAPI(title="FastAPI with Docker", lifespan=lifespan)


class Item(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    description: str | None = None
    price: Annotated[float, Field(ge=0, allow_inf_nan=False)]


@app.middleware("http")
async def log_request(request, call_next):
    response = await call_next(request)
    response.headers["X-Instance-ID"] = socket.gethostname()
    logger.info("%s %s status=%s", request.method, request.url.path, response.status_code)
    return response


@app.get("/")
def root():
    return {"message": "Hello from FastAPI in Docker!"}


@app.get("/health")
def health():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        cache.ping()
    finally:
        conn.close()
    return {"status": "healthy"}


@app.post("/items/", status_code=201)
def create_item(item: Item):
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO items (name, description, price) VALUES (%s, %s, %s)",
                (item.name, item.description, item.price),
            )
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=400, detail="Item already exists")
    finally:
        conn.close()
    try:
        with cache.pipeline() as pipe:
            pipe.incr("items:version")
            pipe.delete(CACHE_KEY)
            pipe.execute()
    except RedisError:
        logger.exception("Cache invalidation failed")
    logger.info("Item created name=%s", item.name)
    return {"message": f"Item {item.name} created"}


@app.get("/items/", response_model=list[Item])
def get_items(response: Response):
    # WATCH не позволяет конкурентному GET восстановить старый кэш после POST.
    with cache.pipeline() as pipe:
        try:
            pipe.watch(CACHE_KEY, "items:version")
            cached = pipe.get(CACHE_KEY)
            if cached is not None:
                response.headers["X-Cache"] = "HIT"
                return json.loads(cached)
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT name, description, price FROM items ORDER BY id")
                    items = [Item(name=r[0], description=r[1], price=r[2]) for r in cur.fetchall()]
            finally:
                conn.close()
            pipe.multi()
            pipe.setex(CACHE_KEY, CACHE_TTL, json.dumps([i.model_dump() for i in items]))
            pipe.execute()
            response.headers["X-Cache"] = "MISS"
            return items
        except RedisError:
            logger.warning("Cache unavailable or changed concurrently; reading PostgreSQL")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name, description, price FROM items ORDER BY id")
            items = [Item(name=r[0], description=r[1], price=r[2]) for r in cur.fetchall()]
    finally:
        conn.close()
    response.headers["X-Cache"] = "BYPASS"
    return items
