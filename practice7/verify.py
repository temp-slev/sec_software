"""Проверка API через Ingress; BASE_URL указывает на вход контроллера."""
import json
import os
import urllib.error
import urllib.request
import uuid

BASE_URL = os.getenv('BASE_URL', 'http://localhost:18087')


def request(path, data=None, expected=200):
    req = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Host': 'practice7.local', 'Content-Type': 'application/json'},
    )
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    body = json.load(response)
    assert response.status == expected, (response.status, body)
    return body


assert request('/health')['status'] == 'healthy'
assert request('/version') == {'version': '1.0.0'}
print('Ingress Host=practice7.local: /health=200, /version=1.0.0 из ConfigMap')
item = {'name': 'Laptop-' + uuid.uuid4().hex[:8], 'price': 999.99}
created = request('/items/', item, 201)
assert created in request('/items/')
request('/items/', item, 400)
request('/items/', {'name': 'negative', 'price': -1}, 422)
print('PostgreSQL: создание=201, чтение=200, дубликат=400, неверная цена=422')
print('Созданный объект:', created)
