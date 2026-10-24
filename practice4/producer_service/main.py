import json
import os
from contextlib import asynccontextmanager

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Прямое подключение к брокеру: localhost:9092, через HAProxy: localhost:9093
BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


# Модель данных для заказа
class Order(BaseModel):
    order_id: int
    user_id: int
    product: str
    quantity: int


# Модель данных для уведомления
class Notification(BaseModel):
    user_id: int
    message: str


# Модель данных для сообщения об ошибке
class ErrorMessage(BaseModel):
    source: str
    message: str
    code: int = 500


# Инициализация продюсера
producer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global producer
    producer = AIOKafkaProducer(
        bootstrap_servers=BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    await producer.start()
    print(f"Kafka Producer started ({BOOTSTRAP_SERVERS})")
    yield
    await producer.stop()
    print("Kafka Producer stopped")


app = FastAPI(title="Producer Service", lifespan=lifespan)


async def publish(topic: str, value: dict):
    """Отправка сообщения; если брокер недоступен, возвращается 503."""
    try:
        await producer.send_and_wait(topic, value=value)
    except KafkaError as e:
        raise HTTPException(status_code=503, detail=f"Kafka is unavailable: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/orders/")
async def create_order(order: Order):
    """Публикация сообщения о заказе в топик orders"""
    await publish("orders", order.model_dump())
    return {"status": "success", "message": f"Order {order.order_id} sent to Kafka"}


@app.post("/notify/")
async def send_notification(notification: Notification):
    """Публикация уведомления в топик notifications"""
    await publish("notifications", notification.model_dump())
    return {
        "status": "success",
        "message": f"Notification sent to user {notification.user_id}",
    }


@app.post("/errors/")
async def send_error(error: ErrorMessage):
    """Публикация сообщения об ошибке в топик errors"""
    await publish("errors", error.model_dump())
    return {"status": "success", "message": f"Error from {error.source} sent to Kafka"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
