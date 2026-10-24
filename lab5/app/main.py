import json
import logging
import random
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from prometheus_fastapi_instrumentator import Instrumentator

# Поля стандартного LogRecord: всё остальное считается дополнительными полями (extra)
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}


class JSONFormatter(logging.Formatter):
    """Структурированный JSON-лог: стандартные поля плюс extra из logger.info(..., extra=...)."""

    def format(self, record):
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        log_record.update(
            {k: v for k, v in vars(record).items() if k not in _STANDARD}
        )
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)


logger = logging.getLogger("app")
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

app = FastAPI(title="FastAPI with Structured Logging")
Instrumentator(should_group_status_codes=False).instrument(app).expose(app)


# Middleware для логирования всех запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        if request.url.path != "/metrics":
            level = logging.ERROR if status_code >= 500 else logging.INFO
            logger.log(
                level,
                "Request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration": round(time.perf_counter() - start, 4),
                    "client_ip": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent"),
                },
            )


@app.get("/")
async def root():
    logger.info("Root endpoint called")
    return {"message": "Hello!"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/cpu")
async def cpu_load():
    logger.info("CPU load endpoint called")
    for _ in range(10_000_000):
        pass
    return {"status": "loaded"}


@app.get("/crash")
async def crash():
    """Аномалия для задания 3: ошибка с вероятностью 30%."""
    if random.random() < 0.3:
        logger.error("Random failure in /crash", extra={"reason": "simulated_failure"})
        raise HTTPException(status_code=500, detail="Simulated failure")
    return {"status": "ok"}
