import json
import os
from contextlib import asynccontextmanager

import aio_pika
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
connection = None
channel = None


class Order(BaseModel):
    order_id: int
    user_id: int
    product: str
    quantity: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    global connection, channel
    connection = await aio_pika.connect_robust(RABBIT_URL)
    channel = await connection.channel()
    await channel.declare_queue("orders", durable=True)
    yield
    await connection.close()


app = FastAPI(title="RabbitMQ Producer", lifespan=lifespan)


@app.post("/orders/")
async def create_order(order: Order):
    try:
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(order.model_dump()).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="orders",
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"RabbitMQ is unavailable: {e}")
    return {"status": "success", "message": f"Order {order.order_id} sent to RabbitMQ"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
