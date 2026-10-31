# Практическое занятие №12. Prometheus в локальном Kubernetes

Студенты: Рудометкин Станислав Владимирович, Татенко Мария Станиславовна, группа 22-к-кб1, вариант 19.

FastAPI инструментирован `prometheus-fastapi-instrumentator`. Prometheus из Helm-чарта
`kube-prometheus-stack` 92.11.0 обнаруживает обе реплики приложения через ServiceMonitor.
Среда — Kubernetes Docker Desktop, namespace приложения `practice12`, мониторинга `monitoring`.

## Состав

| Путь | Назначение |
|---|---|
| `app/`, `Dockerfile` | образ `practice12-fastapi:v1`, эндпоинты `/`, `/health`, `/cpu`, `/fail`, `/metrics` |
| `k8s/app.yaml` | Deployment, Service и ServiceMonitor |
| `monitoring/values.yaml` | параметры общего Prometheus/Grafana-стека практик 12 и 13 |
| `grafana/` | собственный дашборд и ConfigMap для автоматической загрузки |
| `deploy.sh` | воспроизводимое развёртывание |
| `load.py`, `verify.py`, `logs/` | проверки двух целей Prometheus и протоколы |

## Выполнение и результаты

1. Образ собран локально и использован с `imagePullPolicy: Never`. Приложение сначала
   развёрнуто с одной репликой; `ENABLE_METRICS=true` включает инструментацию.
2. Service с именованным портом `metrics` обнаруживается ServiceMonitor по метке
   `app: practice12-fastapi`, `/metrics` опрашивается каждые 15 секунд.
3. Prometheus установлен через Helm; настроен поиск ServiceMonitor без обязательного
   совпадения меток Helm-релиза. В Targets обе цели приложения имеют статус UP.
4. **Задание 1:** Counter `my_custom_counter` увеличивается на каждом запросе `/`.
   В формате Prometheus он публикуется как `my_custom_counter_total`; метрика
   проверена на `/metrics` и в Prometheus.
5. **Задание 2:** приложение масштабировано с одной реплики до двух, READY 2/2;
   Prometheus возвращает счётчики обеих реплик с разными метками `pod`.
6. **Задание 3 (дополнительное):** создан и загружен собственный дашборд Grafana
   `FastAPI Monitoring — Practice 12` с восемью панелями. Источник Prometheus доступен,
   все PromQL-запросы панелей возвращают данные.

Протоколы: `logs/scaling.log`, `logs/prometheus-check.log`, `logs/metrics-check.log`,
`logs/dashboard-check.log`, `logs/cluster-survey.log`. Нагрузка на `/` и `/cpu` выполнена;
фактическая интенсивность и счётчики зафиксированы в результатах проверки.

## Исправления примера и особенности среды

- Используется Kubernetes Docker Desktop вместо Minikube; локальные образы доступны
  кластеру напрямую. Включение Minikube не требуется.
- В методичке указан `fastapi_requests_total`, но установленная библиотека публикует
  `http_requests_total`. Используется реально проверенный запрос
  `sum(rate(http_requests_total{namespace="practice12"}[1m]))`.
- kube-prometheus-stack не заменяет Metrics Server: Prometheus собирает временные ряды,
  Metrics Server обслуживает `metrics.k8s.io` для `kubectl top` и HPA. Он сохранён в кластере.
- Метка `release` не имеет специального смысла для Kubernetes: её влияние зависит от
  селекторов Prometheus и ServiceMonitor. В этой работе selectors явно настроены.
- `/health` и `/metrics` исключены из метрик запросов, чтобы probes и scrape не создавали
  искусственную прикладную нагрузку. CPU-операция выполнена в `def`, через пул потоков.

## Ответы на контрольные вопросы

1. **Инструментация.** Middleware автоматически учитывает число запросов, длительность,
   размеры запросов и ответов, группируя данные по маршруту, методу и статусу.
2. **ServiceMonitor.** CRD оператора Prometheus описывает, какие Service и порты
   опрашивать, путь метрик и интервал. Selector выбирает Service, а его endpoints — поды.
3. **release.** Это обычная метка, используемая Helm-чартом для отбора ресурсов.
   Здесь ServiceMonitor выбирает Service по `app`, а Prometheus принимает ServiceMonitor
   с любыми метками благодаря `serviceMonitorSelectorNilUsesHelmValues: false`.
4. **Типы.** Counter растёт до перезапуска (запросы); Gauge может расти и падать (память,
   число активных задач); Histogram считает наблюдения по buckets и позволяет вычислять
   квантили и агрегировать данные разных реплик.
5. **docker-env.** В Minikube эта команда переключает Docker CLI на daemon внутри
   Minikube, чтобы собранный образ оказался у узла. Альтернатива — `minikube image load`.
   В Docker Desktop используется общая локальная среда, переключение не требуется.

После сохранения результатов проверочные поды остановлены, общий Helm-стек удалён
для освобождения ресурсов. Конфигурация и протоколы сохранены в репозитории.
