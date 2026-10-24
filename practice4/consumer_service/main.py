import asyncio
import json
import os
from contextlib import asynccontextmanager

from aiokafka import AIOKafkaConsumer
from fastapi import FastAPI

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
PROCESSING_DELAY = float(os.getenv("PROCESSING_DELAY", "1"))

# Хранилище полученных сообщений (в памяти)
received_orders = []
received_notifications = []
received_errors = []

consumers = []
background_tasks = set()  # ссылки на задачи, чтобы их не удалил сборщик мусора


def make_consumer(topic: str, group_id: str) -> AIOKafkaConsumer:
    return AIOKafkaConsumer(
        topic,
        bootstrap_servers=BOOTSTRAP_SERVERS,
        group_id=group_id,
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )


async def process(kind: str, storage: list, value: dict):
    """Обработка одного сообщения в отдельной корутине (имитация работы)."""
    await asyncio.sleep(PROCESSING_DELAY)
    storage.append(value)
    print(f"{kind} received: {value}")


async def consume(consumer: AIOKafkaConsumer, kind: str, storage: list):
    """Фоновая задача: каждое сообщение обрабатывается через asyncio.create_task()."""
    async for msg in consumer:
        task = asyncio.create_task(process(kind, storage, msg.value))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)


@asynccontextmanager
async def lifespan(app: FastAPI):
    specs = [
        ("orders", "orders-group", "Order", received_orders),
        ("notifications", "notifications-group", "Notification", received_notifications),
        ("errors", "errors-group", "Error", received_errors),
    ]
    readers = []
    for topic, group, kind, storage in specs:
        consumer = make_consumer(topic, group)
        await consumer.start()
        consumers.append(consumer)
        readers.append(asyncio.create_task(consume(consumer, kind, storage)))
    print("Kafka Consumers started")
    yield
    for reader in readers:
        reader.cancel()
    for consumer in consumers:
        await consumer.stop()


app = FastAPI(title="Consumer Service", lifespan=lifespan)


@app.get("/orders/")
async def get_orders():
    """Получение всех обработанных заказов"""
    return {"orders": received_orders, "count": len(received_orders)}


@app.get("/notifications/")
async def get_notifications():
    """Получение всех обработанных уведомлений"""
    return {"notifications": received_notifications, "count": len(received_notifications)}


@app.get("/errors/")
async def get_errors():
    """Получение всех обработанных сообщений об ошибках"""
    return {"errors": received_errors, "count": len(received_errors)}


@app.get("/health")
async def health():
    return {"status": "healthy"}
