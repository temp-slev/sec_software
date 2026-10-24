from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="QA Demo")


class Item(BaseModel):
    name: str
    price: float


items_db = {}


@app.get("/")
async def root():
    return {"message": "Hello, QA!"}


@app.post("/items/", status_code=201)
async def create_item(item: Item):
    if item.name in items_db:
        raise HTTPException(status_code=400, detail="Item already exists")
    items_db[item.name] = item
    return {"message": f"Item {item.name} created"}


@app.get("/items/{name}")
async def get_item(name: str):
    if name not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    return items_db[name]


@app.get("/items/")
async def get_all_items() -> List[Item]:
    return list(items_db.values())


@app.delete("/items/{name}")
async def delete_item(name: str):
    if name not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    del items_db[name]
    return {"message": f"Item {name} deleted"}
