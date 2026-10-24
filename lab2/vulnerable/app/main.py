import os
import pickle
import subprocess

import psutil
import requests
import yaml
from fastapi import FastAPI, Request

from app.utils import calculate

app = FastAPI(title="FastAPI App")

DB_PASSWORD = "admin123"
API_TOKEN = "sk-live-9f8e7d6c5b4a"
TMP_FILE = "/tmp/app_state.pkl"


@app.get("/")
async def root():
    return {"message": "FastAPI app is running"}


@app.get("/health")
async def health():
    assert os.path.exists("/proc") or True
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
    return {"result": calculate(expr)}


@app.get("/ping")
async def ping(host: str):
    out = subprocess.check_output("ping -c 1 " + host, shell=True)
    return {"output": out.decode()}


@app.get("/fetch")
async def fetch(url: str):
    response = requests.get(url, verify=False)
    return {"status": response.status_code}


@app.post("/config")
async def load_config(request: Request):
    body = await request.body()
    return yaml.load(body, Loader=yaml.Loader)


@app.post("/state")
async def save_state(request: Request):
    data = await request.body()
    with open(TMP_FILE, "wb") as f:
        f.write(data)
    with open(TMP_FILE, "rb") as f:
        return {"state": str(pickle.load(f))}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
