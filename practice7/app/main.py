import os
import socket
from contextlib import asynccontextmanager

import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


def connect():
    return psycopg2.connect(
        host=os.environ['DB_HOST'], dbname=os.environ['DB_NAME'],
        user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], connect_timeout=5,
    )


@asynccontextmanager
async def lifespan(app):
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(7007)')
            cur.execute('CREATE TABLE IF NOT EXISTS items (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, price DOUBLE PRECISION NOT NULL)')
    finally:
        conn.close()
    yield


app = FastAPI(title='FastAPI on Kubernetes', lifespan=lifespan)


class Item(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: float = Field(ge=0, allow_inf_nan=False)


@app.get('/')
def root():
    return {'message': 'Hello from Kubernetes!', 'pod': socket.gethostname()}


@app.get('/health')
def health():
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
    finally:
        conn.close()
    return {'status': 'healthy'}


@app.get('/version')
def version():
    return {'version': os.getenv('APP_VERSION', 'unknown')}


@app.post('/items/', status_code=201)
def create_item(item: Item):
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute('INSERT INTO items (name, price) VALUES (%s, %s) RETURNING id', (item.name, item.price))
            item_id = cur.fetchone()[0]
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=400, detail='Item already exists')
    finally:
        conn.close()
    return {'id': item_id, **item.model_dump()}


@app.get('/items/')
def get_items():
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, name, price FROM items ORDER BY id')
            return [{'id': row[0], 'name': row[1], 'price': row[2]} for row in cur.fetchall()]
    finally:
        conn.close()
