import os
import socket

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="FastAPI Monitoring Practice 13")
my_custom_counter = Counter("my_custom_counter", "Number of requests to the root endpoint")
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_respect_env_var=True,
    excluded_handlers=["/health", "/metrics"],
).instrument(app).expose(app)


@app.get("/")
def root():
    my_custom_counter.inc()
    return {"message": "Hello from monitored FastAPI!", "pod": socket.gethostname()}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/cpu")
def cpu_load():
    for _ in range(10_000_000):
        pass
    return {"status": "loaded"}


@app.get("/fail")
def fail():
    """Контролируемая ошибка для проверки оповещений учебного стенда."""
    raise HTTPException(status_code=500, detail="Simulated failure")
