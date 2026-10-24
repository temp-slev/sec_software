"""Сравнение Kafka и RabbitMQ: N сообщений от продюсера до консьюмера.

Запуск: python benchmark.py [N]. Требуются запущенные контейнеры kafka и rabbitmq.
"""
import asyncio
import json
import statistics
import sys
import time

import aio_pika
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
TOPIC = "benchmark"


def report(name, sent_total, latencies, total):
    lat = sorted(latencies)
    print(
        f"{name:9} | {len(lat)} сообщений | всего {total:.2f} с | "
        f"{len(lat) / total:7.0f} сообщ./с | задержка средняя {statistics.mean(lat) * 1000:7.1f} мс, "
        f"p95 {lat[int(len(lat) * 0.95)] * 1000:7.1f} мс"
    )


async def bench_kafka():
    producer = AIOKafkaProducer(bootstrap_servers="localhost:9092")
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers="localhost:9092",
        group_id=f"bench-{time.time_ns()}",
        auto_offset_reset="latest",
    )
    await producer.start()
    await consumer.start()
    # дожидаемся назначения партиций до старта замера
    while not consumer.assignment():
        await asyncio.sleep(0.1)
    latencies = []

    async def read():
        async for msg in consumer:
            latencies.append(time.perf_counter() - json.loads(msg.value)["t"])
            if len(latencies) == N:
                return

    reader = asyncio.create_task(read())
    start = time.perf_counter()
    for i in range(N):
        await producer.send(TOPIC, json.dumps({"i": i, "t": time.perf_counter()}).encode())
    await producer.flush()
    await asyncio.wait_for(reader, 120)
    total = time.perf_counter() - start
    await producer.stop()
    await consumer.stop()
    report("Kafka", N, latencies, total)


async def bench_rabbit():
    connection = await aio_pika.connect_robust("amqp://guest:guest@localhost:5672/")
    channel = await connection.channel()
    queue = await channel.declare_queue("benchmark", durable=True)
    await queue.purge()
    latencies = []
    done = asyncio.Event()

    async def on_message(message):
        async with message.process():
            latencies.append(time.perf_counter() - json.loads(message.body)["t"])
            if len(latencies) == N:
                done.set()

    await queue.consume(on_message)
    start = time.perf_counter()
    for i in range(N):
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps({"i": i, "t": time.perf_counter()}).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="benchmark",
        )
    await asyncio.wait_for(done.wait(), 120)
    total = time.perf_counter() - start
    await connection.close()
    report("RabbitMQ", N, latencies, total)


async def main():
    print(f"Сообщений: {N}, один продюсер, один консьюмер, локальные контейнеры Docker")
    await bench_rabbit()
    await bench_kafka()


asyncio.run(main())
