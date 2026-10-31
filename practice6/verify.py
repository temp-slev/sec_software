"""Проверка API через Nginx; выполняется внутри сети Docker Compose."""
import json
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://nginx"


def call(method, path, body=None, expected=200):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    payload = json.loads(response.read())
    assert response.code == expected, (method, path, response.code, payload)
    return payload, response.headers


print("Nginx: GET / ->", call("GET", "/")[0])
print("GET /health ->", call("GET", "/health")[0])
name = "Laptop-" + uuid.uuid4().hex[:8]
item = {"name": name, "description": "Gaming laptop", "price": 999.99}
print("POST /items/ ->", call("POST", "/items/", item, 201)[0])
items, headers = call("GET", "/items/")
assert item in items
assert headers["X-Cache"] == "MISS", headers
print("Первое чтение: X-Cache=MISS; товар присутствует в PostgreSQL")
items, headers = call("GET", "/items/")
assert headers["X-Cache"] == "HIT"
print("Повторное чтение: X-Cache=HIT")
print("Дубликат ->", call("POST", "/items/", item, 400)[0])
call("POST", "/items/", {"name": "Negative", "price": -1}, 422)
print("Отрицательная цена -> HTTP 422")
item2 = {"name": name + "-second", "description": None, "price": 10.0}
call("POST", "/items/", item2, 201)
items, headers = call("GET", "/items/")
assert headers["X-Cache"] == "MISS" and item2 in items
print("Добавление товара сбрасывает кэш: X-Cache=MISS, новый товар присутствует")
instances = set()
for _ in range(30):
    _, headers = call("GET", "/")
    instances.add(headers["X-Instance-ID"])
    time.sleep(0.05)
print("Nginx направил запросы на экземпляры:", sorted(instances))
print("API и кэш: все проверки пройдены")
