import ipaddress
import json
import os
import re
import subprocess  # nosec B404 - используется только без shell и с проверенным host
from urllib.parse import urlparse

import psutil
import requests
import yaml
from fastapi import FastAPI, HTTPException, Request

from app.utils import calculate

app = FastAPI(title="FastAPI App")

# Секреты берутся из окружения, а не из исходного кода
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
API_TOKEN = os.getenv("API_TOKEN", "")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

HOSTNAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
ALLOWED_FETCH_HOSTS = {"example.com", "jsonplaceholder.typicode.com"}


@app.get("/")
async def root():
    return {"message": "FastAPI app is running"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/cpu")
async def cpu():
    return {"cpu_percent": psutil.cpu_percent(interval=0.1)}


@app.get("/metrics")
async def metrics():
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent,
    }


@app.get("/calc")
async def calc(expr: str):
    try:
        return {"result": calculate(expr)}
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
        raise HTTPException(status_code=400, detail="Invalid expression")


def _valid_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return bool(HOSTNAME_RE.match(host))


@app.get("/ping")
async def ping(host: str):
    if not _valid_host(host):
        raise HTTPException(status_code=400, detail="Invalid host")
    out = subprocess.run(  # nosec B603 B607 - без shell, host проверен _valid_host()
        ["ping", "-c", "1", "--", host],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return {"output": out.stdout}


@app.get("/fetch")
async def fetch(url: str):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_FETCH_HOSTS:
        raise HTTPException(status_code=400, detail="URL is not allowed")
    response = requests.get(url, timeout=5)  # проверка сертификата включена по умолчанию
    return {"status": response.status_code}


@app.post("/config")
async def load_config(request: Request):
    body = await request.body()
    try:
        return yaml.safe_load(body)
    except yaml.YAMLError:
        raise HTTPException(status_code=400, detail="Invalid YAML")


@app.post("/state")
async def save_state(request: Request):
    try:
        data = json.loads(await request.body())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    with open(STATE_FILE, encoding="utf-8") as f:
        return {"state": json.load(f)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=os.getenv("APP_HOST", "127.0.0.1"), port=8000)
