# Практическое занятие №4. Apache Kafka, HAProxy, RabbitMQ

Студент: Рудометкин Станислав Владимирович, группа 22-к-кб1, вариант 19.

Система обмена сообщениями на Kafka: брокер с веб-интерфейсом, топики `orders`,
`notifications` (и `errors` по заданию 1), Producer и Consumer на FastAPI,
балансировка через HAProxy и сравнение с RabbitMQ.

## Состав

| Путь | Назначение |
|---|---|
| `docker-compose.yml` | ZooKeeper, Kafka, Kafka UI (порт 8080), HAProxy (9093), RabbitMQ (5672, 15672) |
| `haproxy.cfg` | TCP-балансировщик перед Kafka |
| `producer_service/` | Producer: `POST /orders/`, `/notify/`, `/errors/` |
| `consumer_service/` | Consumer: `GET /orders/`, `/notifications/`, `/errors/` |
| `rabbitmq_comparison/` | Producer и Consumer для RabbitMQ, `benchmark.py` |
| `postman_collection.json` | запросы для Postman |
| `logs/` | протоколы реальных запусков |

## Запуск

```bash
docker compose up -d
# топики (auto-create отключён, партиции задаются явно)
docker exec kafka kafka-topics --create --topic orders --bootstrap-server localhost:9092 --partitions 3 --replication-factor 1
docker exec kafka kafka-topics --create --topic notifications --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
docker exec kafka kafka-topics --create --topic errors --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
docker exec kafka kafka-topics --list --bootstrap-server localhost:9092

pip install -r producer_service/requirements.txt
cd consumer_service && uvicorn main:app --port 8001      # терминал 1
cd producer_service && uvicorn main:app --port 8000      # терминал 2
```

Kafka UI: http://localhost:8080, RabbitMQ: http://localhost:15672 (guest / guest).
В протоколах сервисы запускались на портах 8100 и 8101, потому что порт 8000 на
машине был занят; в коллекции Postman указаны эти порты, при запуске на 8000/8001
замените их.

Через HAProxy: `KAFKA_BOOTSTRAP_SERVERS=localhost:9093 uvicorn main:app --port 8000`.

## Что отличается от текста задания

- Образы `cp-zookeeper` и `cp-kafka` закреплены на версии 7.6.1: тег `latest` перешёл на
  Kafka без ZooKeeper.
- В исходном `docker-compose.yml` брокер объявляет только `localhost:9092`, из-за чего
  Kafka UI внутри Docker не может подключиться к `kafka:9092`. Поэтому настроены три
  listener'а: `INTERNAL` (`kafka:29092`, для контейнеров), `EXTERNAL` (`localhost:9092`, для
  сервисов на хосте) и `BALANCED` (`localhost:9093`, для клиентов за HAProxy).
- В `haproxy.cfg` вместо `localhost:9092` указан `kafka:9094`: внутри контейнера
  `localhost` — это сам HAProxy.
- В моделях используется `model_dump()` вместо устаревшего `.dict()`.
- Consumer читает с `auto_offset_reset="earliest"`, чтобы не терять сообщения,
  отправленные до подключения группы.

## Результаты

| Проверка | Результат | Протокол |
|---|---|---|
| Топики | `orders` — 3 партиции, `notifications` и `errors` — по одной | `logs/topics.log` |
| Kafka UI | кластер `local-kafka` online, 1 брокер, топики видны | `logs/kafka-ui-check.log` |
| Producer → Consumer | заказы, уведомление и ошибка дошли до Consumer | `logs/direct-test.log` |
| HAProxy | продюсер подключён к `localhost:9093`, сообщение доставлено, сессия видна в логе HAProxy | `logs/haproxy-and-parallel.log` |
| Задание 1 | топик `errors`, `POST /errors/` в Producer, чтение в Consumer | `logs/direct-test.log` |
| Задание 2 | каждое сообщение обрабатывается через `asyncio.create_task()` с `sleep(1)`; 5 сообщений обработаны за 1,09 с вместо ~5 с | `logs/haproxy-and-parallel.log` |
| Задание 3 | Producer и Consumer для RabbitMQ работают, сравнение — `benchmark.py` | `logs/rabbitmq-test.log`, `logs/benchmark.log` |

Если брокер недоступен, Producer отвечает `503` с описанием ошибки (`KafkaError`), а не
падает.

### Сравнение Kafka и RabbitMQ (задание 3)

Запуск `python rabbitmq_comparison/benchmark.py 2000` (для него нужен топик
`benchmark`: `kafka-topics --create --topic benchmark ...`), три прогона, локальные
контейнеры, 2000 сообщений:

| Брокер | Время | Пропускная способность | Задержка (средняя, p95) |
|---|---|---|---|
| RabbitMQ | ~1,26 с | ~1590 сообщ./с | 0,5 мс, 0,5 мс |
| Kafka | ~0,05 с | ~37 000–42 000 сообщ./с | ~14 мс, ~20 мс |

Kafka быстрее по пропускной способности: продюсер отправляет пачками без ожидания
подтверждения каждого сообщения. RabbitMQ доставляет отдельное сообщение быстрее (меньше
задержка), но в тесте каждая публикация ждёт подтверждения, что ограничивает
пропускную способность. Сравнение приблизительное: один продюсер, одна машина, разные
режимы подтверждения.

## Ответы на контрольные вопросы

1. **Kafka и RabbitMQ.** Kafka — распределённый журнал: сообщения хранятся на диске
   заданное время, потребители читают независимо и могут перечитать с нужной позиции;
   рассчитана на большие потоки и потоковую обработку. RabbitMQ — классический брокер
   очередей: сообщение доставляется потребителю и удаляется после подтверждения, гибкая
   маршрутизация (exchange), приоритеты, низкая задержка. Kafka — для событий большого
   объёма, аналитики, event sourcing; RabbitMQ — для задач и RPC с гибкой маршрутизацией.
2. **Партиции.** Топик делится на партиции; порядок гарантируется внутри партиции.
   Партиции распределяются по брокерам и позволяют нескольким потребителям группы читать
   параллельно, поэтому пропускная способность растёт с их числом.
3. **Consumer group.** Потребители с одним `group_id` делят партиции топика между собой:
   каждая партиция читается одним членом группы, поэтому сообщения не дублируются, а
   нагрузка распределяется. Разные группы получают все сообщения независимо. При
   добавлении или отказе потребителя происходит перебалансировка.
4. **HAProxy.** Единая точка входа и распределение TCP-соединений между брокерами,
   проверки доступности (`check`), скрытие адресов брокеров. Алгоритмы: `roundrobin`,
   `leastconn`, `source`, `static-rr`, `first`, `uri`, `random`. Для Kafka важно, чтобы
   брокеры объявляли адрес балансировщика в `advertised.listeners`, иначе клиент после
   получения метаданных подключится напрямую.
5. **Гарантии доставки.** По умолчанию — at-least-once (возможны дубликаты при
   повторах). Exactly-once: идемпотентный продюсер (`enable.idempotence=true`),
   транзакции (`transactional.id`) и у потребителей `isolation.level=read_committed`;
   либо идемпотентная обработка на стороне потребителя.
6. **Kafka UI.** Просмотр брокеров, топиков, партиций и конфигурации, создание и удаление
   топиков, просмотр и отправка сообщений, мониторинг consumer groups и лагов, просмотр
   схем и коннекторов.
7. **aiokafka.** FastAPI работает на asyncio: синхронный `kafka-python` блокирует цикл
   событий на время сетевых вызовов и замедляет все запросы, а `aiokafka` использует
   `await` и не блокирует обработку других запросов.
8. **Недоступный брокер.** Обернуть отправку в `try/except KafkaError`, задать таймауты
   и повторы, вернуть клиенту `503`, залогировать ошибку; для критичных данных — локальный
   буфер или outbox-таблица с повторной отправкой, health-проверка брокера.
