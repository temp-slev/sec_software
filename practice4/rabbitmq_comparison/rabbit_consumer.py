import asyncio
import json
import os
from contextlib import asynccontextmanager

import aio_pika
from fastapi import FastAPI

RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
received_orders = []
connection = None


async def on_message(message: aio_pika.IncomingMessage):
    async with message.process():  # ack после успешной обработки
        received_orders.append(json.loads(message.body))
        print(f"Order received: {received_orders[-1]}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global connection
    connection = await aio_pika.connect_robust(RABBIT_URL)
    channel = await connection.channel()
    queue = await channel.declare_queue("orders", durable=True)
    await queue.consume(on_message)
    yield
    await connection.close()


app = FastAPI(title="RabbitMQ Consumer", lifespan=lifespan)


@app.get("/orders/")
async def get_orders():
    return {"orders": received_orders, "count": len(received_orders)}


@app.get("/health")
async def health():
    return {"status": "healthy"}
