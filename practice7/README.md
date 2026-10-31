# Практическое занятие №7. Kubernetes

Студенты: Рудометкин Станислав Владимирович, Татенко Мария Станиславовна, группа 22-к-кб1, вариант 19.

FastAPI развёрнут в локальном Kubernetes Docker Desktop (один узел arm64) в namespace
`practice7`. Deployment содержит две реплики, Service — NodePort 30080. Ingress Traefik
направляет запросы хоста `practice7.local` на приложение. PostgreSQL хранит товары на PVC.

## Состав

| Путь | Назначение |
|---|---|
| `app/main.py`, `app/requirements.txt`, `Dockerfile` | приложение и локальный образ `practice7-fastapi:v1` |
| `k8s/namespace.yaml`, `k8s/config.yaml` | namespace, ConfigMap с APP_VERSION и параметрами БД, демонстрационный Secret |
| `k8s/deployment.yaml`, `k8s/service.yaml` | приложение, NodePort и Ingress |
| `k8s/postgres.yaml` | PostgreSQL, Service и PersistentVolumeClaim |
| `k8s/traefik-values.yaml` | параметры Ingress-контроллера Traefik |
| `deploy.sh` | воспроизводимое развёртывание в текущем локальном Kubernetes |
| `verify.py`, `logs/` | проверка API и результаты выполненных операций |

## Ход работы и результаты

- Узел Kubernetes v1.36.1 в состоянии Ready. Образ собран в Docker Desktop; он доступен
  контейнерной среде Kubernetes, поэтому `imagePullPolicy: Never` не обращается к реестру.
- Deployment сначала запущен с двумя репликами, затем масштабирован до трёх (READY 3/3)
  и возвращён к двум. Протокол: `logs/scaling.log`.
- NodePort `http://localhost:30080/health` ответил HTTP 200. Ingress проверен на входе
  контроллера через заголовок `Host: practice7.local`, без изменения системного hosts.
- Проверены `/health`, `/version`, создание и чтение товаров. ConfigMap подключён через
  `envFrom`; `/version` вернул `1.0.0` (**задание 1**).
- Ingress с хостом `practice7.local` маршрутизирует запросы к `fastapi-service` (**задание 2**).
- PostgreSQL использует PVC `postgres-data`, статус Bound, объём 1 GiB. После удаления пода
  PostgreSQL Deployment создал новый под, а созданный товар сохранился (**задание 3**).
- `kubectl logs`, `describe`, `exec`, `top` и состояние сервисов сохранены в `logs/`.
- После проверки Deployment приложения, Service и Ingress удалены; PostgreSQL остановлен,
  PVC сохранён. Проверочные Helm-релизы удалены (`logs/cleanup.log`).

Таблица `items` создаётся при старте приложения; advisory lock предотвращает конфликт
создания таблицы двумя одновременно стартующими репликами. SQL параметризован, соединения
закрываются, дубликат имени даёт 400, неверная цена — 422.

## Особенности локального окружения

Вместо Minikube использован уже запущенный Kubernetes Docker Desktop. Поэтому не требуются
`minikube start`, `image load`, `docker-env`, `service` и `dashboard`; доступ к кластеру,
образам и сервисам обеспечивает Docker Desktop. Это адаптация окружения относительно
методички. Ingress реализован отдельным контроллером Traefik (Helm chart 42.2.0), а не
аддоном Minikube. Metrics Server установлен для `kubectl top`.

## Ответы на контрольные вопросы

1. **Minikube.** Создаёт локальный учебный Kubernetes на одном или нескольких узлах;
   production-кластер обычно имеет отказоустойчивый control plane, рабочие узлы,
   сетевую и дисковую инфраструктуру, резервирование и обслуживание.
2. **Контроллеры.** Deployment управляет взаимозаменяемыми репликами приложения;
   StatefulSet даёт устойчивые имена и привязки к томам; DaemonSet запускает под на
   каждом подходящем узле, например агент сбора логов.
3. **Service.** ClusterIP доступен внутри кластера; NodePort добавляет порт на узлах;
   LoadBalancer запрашивает внешний балансировщик; ExternalName возвращает DNS-алиас.
   NodePort удобен для локального доступа и простых внешних балансировщиков.
4. **imagePullPolicy.** Never подходит для заранее загруженного локального образа и
   запрещает скачивание. Это не универсальное требование Minikube: IfNotPresent тоже
   использует локальный образ, а Always требует обращения к реестру.
5. **Масштабирование.** Ручное: `kubectl scale deployment fastapi-deployment --replicas=3
   -n practice7` либо изменение `spec.replicas`; автоматическое — HPA по метрикам.
6. **CrashLoopBackOff.** `kubectl logs --previous`, `describe pod`, `get events`, проверка
   exit code/OOMKilled, переменных, команд запуска, probes, ресурсов и зависимостей.
7. **Ingress.** Маршрутизирует HTTP/HTTPS по хостам и путям через Ingress-контроллер.
   LoadBalancer предоставляет сетевую точку входа для Service; несколько приложений
   могут совместно использовать один вход Ingress.
8. **Хранение.** Данные выносятся из слоя контейнера в PersistentVolume, запрошенный
   через PVC. Перезапуск пода не удаляет PVC; удаление самого PVC может удалить данные
   в зависимости от reclaimPolicy. Для БД также нужны резервные копии.
