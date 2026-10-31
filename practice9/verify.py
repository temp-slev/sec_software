"""Интеграционная проверка работающего S3-сервиса (из контейнера app).

Все запросы идут в FastAPI, бинарные данные — в реальный MinIO.
"""
import concurrent.futures
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import boto3

BASE = os.getenv("TEST_BASE_URL", "http://localhost:8000")


def request(method, path, data=None, headers=None, expected=200):
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers or {})
    try:
        response = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as error:
        response = error
    body = response.read()
    assert response.code == expected, (method, path, response.code, body[:300])
    return body, response.headers


def get(path, expected=200):
    body, _ = request("GET", path, expected=expected)
    return json.loads(body)


def upload(key, content):
    path = "/upload/?" + urllib.parse.urlencode({"key": key, "content": content})
    return json.loads(request("POST", path, b"")[0])


assert get("/health")["status"] == "healthy"
assert "data-lake-bucket" in get("/buckets/")["buckets"]
assert get("/objects/sample.json")["data"] == {"id": 1, "name": "Test Record", "value": 42}
print("Инициализация: бакет и sample.json созданы; чтение образца — HTTP 200")

upload("new_data.json", '{"user":"alice","score":100}')
assert get("/objects/new_data.json")["data"]["score"] == 100
upload("nested/note.TXT", "Hello, S3!")
assert get("/objects/nested/note.TXT")["data"] == "Hello, S3!"
print("Загрузка через /upload/: JSON и текст с вложенным ключом прочитаны без изменений")

filtered = get("/objects/?prefix=nested/&file_type=txt")
assert filtered["count"] == 1 and filtered["objects"][0]["key"] == "nested/note.TXT"
assert all(o["key"].lower().endswith(".json") for o in get("/objects/?file_type=.json")["objects"])
print("Фильтрация: prefix и file_type работают совместно, расширения без учёта регистра")

upload("broken.json", "not a JSON document")
aggregate = get("/aggregate/")
assert any(o.get("data", {}).get("score") == 100 for o in aggregate["data"] if isinstance(o.get("data"), dict))
assert {"file": "broken.json", "error": "Invalid JSON"} in aggregate["data"]
print("Агрегация: валидные JSON собраны, ошибочный JSON отмечен отдельно")

body, headers = request("GET", "/download/nested/note.TXT")
assert body == b"Hello, S3!"
assert headers.get_filename() == "note.TXT"
assert headers["Content-Disposition"].startswith("attachment;")
print("Скачивание: attachment, имя note.TXT и содержимое файла корректны")

get("/objects/no-such-key", 404)
request("GET", "/download/no-such-key", expected=404)
get("/objects/?file_type=..", 422)
print("Ошибочные запросы: отсутствующий объект — 404, неверное расширение — 422")

# 12 МиБ > порога 5 МиБ: реальная S3 multipart-загрузка из трёх частей.
payload = bytes(range(256)) * (12 * 1024 * 1024 // 256)
boundary = "practice9-boundary-5e781b"
body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        'filename="large.bin"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
body += payload + f"\r\n--{boundary}--\r\n".encode()
response, _ = request("POST", "/upload-file/?key=large.bin", body,
                      {"Content-Type": f"multipart/form-data; boundary={boundary}"})
result = json.loads(response)
assert result["size"] == len(payload)
assert result["etag"].endswith("-3"), result
received, headers = request("GET", "/download/large.bin")
assert hashlib.sha256(received).digest() == hashlib.sha256(payload).digest()
assert int(headers["Content-Length"]) == len(payload)
get("/objects/large.bin", 415)
print("Multipart: 12 МиБ загружены тремя частями; ETag =", result["etag"])
print("SHA-256 до загрузки и после скачивания совпадают:", hashlib.sha256(received).hexdigest())

filename = "отчёт.txt"
upload(filename, "Текст UTF-8")
received, headers = request("GET", "/download/" + urllib.parse.quote(filename))
assert headers.get_filename() == filename and received.decode() == "Текст UTF-8"
print("UTF-8: имя отчёт.txt и текст корректно передаются при скачивании")

# Проверяем вторую страницу list_objects_v2 (лимит одной страницы — 1000 объектов).
s3 = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"],
                  aws_access_key_id=os.environ["S3_ACCESS_KEY"],
                  aws_secret_access_key=os.environ["S3_SECRET_KEY"], region_name="us-east-1")
bucket = os.environ["S3_BUCKET"]
keys = [f"pagination/{i:04}.txt" for i in range(1005)]
try:
    def seed(key):
        s3.put_object(Bucket=bucket, Key=key, Body=b"page check")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(seed, keys))
    result = get("/objects/?prefix=pagination/&file_type=txt")
    assert result["count"] == 1005
    print("Пагинация: API вернул все 1005 объектов из двух страниц S3")
finally:
    for offset in range(0, len(keys), 1000):
        s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in keys[offset:offset + 1000]]})
    s3.close()
print("Все интеграционные проверки пройдены")
