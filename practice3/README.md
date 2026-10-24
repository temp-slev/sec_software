# Практическое занятие №3. FastAPI, Postman, интеграции

Студент: Рудометкин Станислав Владимирович, группа 22-к-кб1, вариант 19.

Микросервис **User Service** (`user_service/`): CRUD пользователей, валидация через
Pydantic, интеграция с Notification Service, фильтрация, JWT-аутентификация и
запрос к внешнему API.

## Состав

| Файл | Назначение |
|---|---|
| `user_service/main.py` | сервис пользователей (этапы 1–3 и задания 1–3) |
| `user_service/notify_service.py` | эмулятор Notification Service (порт 8001) |
| `user_service/test_main.py` | автотесты (pytest) |
| `user_service/postman_collection.json` | коллекция для импорта в Postman |
| `user_service/run-log.txt` | протокол реального запуска (curl-запросы и ответы) |

## Запуск

```bash
cd user_service
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python notify_service.py            # терминал 1, порт 8001
uvicorn main:app --reload           # терминал 2, порт 8000
```

Swagger: http://127.0.0.1:8000/docs. Тесты: `pytest -q` (7 тестов проходят).

## Реализовано

- **Этап 2.** `POST /users/`, `GET /users/`, `GET /users/{id}`, `PUT /users/{id}`,
  `DELETE /users/{id}`; уникальность email, ошибки 400 и 404.
- **Этап 3.** После создания пользователя сервис отправляет POST на
  `http://localhost:8001/notify/`. Если уведомления недоступны, ошибка
  логируется и пользователь всё равно создаётся.
- **Задание 1.** `GET /users/?min_age=30` возвращает пользователей старше 30.
- **Задание 2.** `POST /signup` и `POST /login` (JWT, HS256, 30 минут). `PUT` и
  `DELETE` по `/users/{id}` без заголовка `Authorization: Bearer <token>` отвечают
  `401`. Пароли хранятся как PBKDF2-хеш с солью. Ключ берётся из переменной
  `SECRET_KEY`.
- **Задание 3.** `GET /users/{id}/posts` обращается к
  `https://jsonplaceholder.typicode.com/posts?userId={id}`. Ошибка статуса внешнего
  API (`httpx.HTTPStatusError`) превращается в `502`, недоступность — в `503`.

## Проверка в Postman

Импортируйте `user_service/postman_collection.json`. Порядок: Create user → List →
Get → Signup → Login (токен сохраняется в переменную `{{token}}` автоматически) →
Update → Delete. Ожидаемые результаты (так же они получены в `run-log.txt`):
`201`, `200`, `200`, `201`, `200`, `200`, `200`. Повторный `DELETE` того же id даёт `404`.

Скриншоты для отчёта: ответ Create user (201), Update без токена (401) и с токеном
(200), консоль Notification Service с сообщением `! Sending notification ...`,
страница `/docs`.

## Ответы на контрольные вопросы

1. **FastAPI и Flask.** FastAPI асинхронный (ASGI), сам валидирует данные по
   аннотациям типов, автоматически строит Swagger/OpenAPI-документацию и имеет
   встроенную систему зависимостей. Во Flask это приходится подключать отдельными
   библиотеками.
2. **Pydantic.** Описывает схемы входных и выходных данных: проверяет типы, возвращает
   `422` при ошибке, сериализует ответ (`response_model`) и даёт схему для документации.
3. **JSON в Postman.** Метод POST, вкладка Body → raw → тип JSON, тело в формате JSON;
   Postman сам ставит `Content-Type: application/json`.
4. **Асинхронный запрос.** Библиотека `httpx` с `httpx.AsyncClient` и `await
   client.post(...)` внутри `async def`-эндпоинта; также подходит `aiohttp`.
5. **Недоступный сервис уведомлений.** Обернуть вызов в `try/except
   httpx.RequestError`, задать `timeout`, залогировать ошибку и вернуть результат,
   не прерывая основную операцию. Для надёжности можно использовать очередь и
   повторные попытки.
6. **Документация.** `/docs` (Swagger UI) и `/redoc`, схема лежит в `/openapi.json`.
   Нужна для просмотра контракта API и для пробных запросов из браузера.
7. **Повторный DELETE.** Отправить `DELETE /users/1` дважды: первый раз ожидаем `200`,
   второй — `404 User not found`. В Postman это проверяется во вкладке Tests, например
   `pm.response.to.have.status(404)`.
