# Лабораторная работа №4 (файл «Лаба 5»). Обследование и логирование облачных систем

Студенты: Рудометкин Станислав Владимирович, Татенко Мария Станиславовна, группа 22-к-кб1, вариант 19.

Стек: FastAPI с JSON-логами и метриками Prometheus в Kubernetes (Docker Desktop), сбор логов
Loki + Promtail, метрики Prometheus (kube-prometheus-stack), визуализация в Grafana,
оповещения через Alertmanager.

## Состав

| Путь | Назначение |
|---|---|
| `app/main.py`, `Dockerfile`, `app/requirements.txt` | приложение: `/`, `/health`, `/cpu`, `/crash`, `/metrics` |
| `k8s/fastapi-app.yaml` | Deployment (2 пода), Service, ServiceMonitor |
| `k8s/loki-values.yaml` | Loki, Promtail, Grafana, правило оповещения по логам |
| `k8s/prometheus-values.yaml` | Prometheus, Alertmanager (получатель — webhook) |
| `k8s/prometheus-datasource.yaml` | источник данных Prometheus для Grafana |
| `k8s/alert-webhook.yaml` | приёмник оповещений (печатает их в лог пода) |
| `grafana/incident-dashboard.json` | дашборд «Incident Investigation Dashboard» |
| `collect_evidence.py` | выгрузка метрик и логов для расследования |
| `INVESTIGATION.md` | отчёт о расследовании инцидента |
| `logs/` | протоколы реальных запусков |

## Развёртывание

Использован Kubernetes из Docker Desktop (одна нода `docker-desktop`) вместо Minikube:
`eval $(minikube docker-env)` не нужен, образ, собранный локально, виден кластеру.

```bash
docker build -t fastapi-logging:latest .

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/
helm repo update
kubectl create namespace monitoring
kubectl create namespace logging

helm install prometheus-stack prometheus-community/kube-prometheus-stack -n monitoring -f k8s/prometheus-values.yaml
helm install loki grafana/loki-stack -n logging -f k8s/loki-values.yaml
helm install metrics-server metrics-server/metrics-server -n kube-system --set 'args={--kubelet-insecure-tls}'
kubectl apply -f k8s/prometheus-datasource.yaml -f k8s/alert-webhook.yaml -f k8s/fastapi-app.yaml

kubectl port-forward -n logging svc/loki-grafana 3000:80            # Grafana: admin / prom-operator
kubectl port-forward -n monitoring svc/prometheus-stack-kube-prom-prometheus 9090:9090
```

Приложение доступно на http://localhost:8090 (порт 8000 на машине занят). Дашборд:
Grafana → Dashboards → Import → загрузить `grafana/incident-dashboard.json`
(источники данных выбираются по именам `Loki` и `Prometheus`).

## Усиление безопасности (по итогам Лабы 6)

Пентест в `lab6/` обнаружил, что у `fastapi-app` не было `securityContext`. Добавлены
`runAsNonRoot`, `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false`,
`capabilities.drop: [ALL]`, `readOnlyRootFilesystem: true` и
`automountServiceAccountToken: false` (приложение не обращается к Kubernetes API).
Подробности — `lab6/FINDINGS.md`.

## Что отличается от текста задания

- Вместо Minikube используется Kubernetes из Docker Desktop; сервис доступен через
  `localhost:8090`, а не через `minikube service`.
- Логи в JSON: в исходном листинге поля из `extra=` терялись (форматтер их не выводил) и
  использовался устаревший `datetime.utcnow()`. Форматтер дополнен выводом `extra`, добавлены
  `exception` и уровень `ERROR` для ответов 5xx.
- `prometheus-fastapi-instrumentator` запущен с `should_group_status_codes=False`, иначе метка
  `status` имела бы значения `5xx`, и запрос `status=~"5.."` из задания ничего бы не нашёл.
- Docker Desktop хранит логи в формате Docker JSON, поэтому в Promtail задан этап `docker: {}`
  (по умолчанию `cri`); без него строка лога приходила в Loki обёрнутой в `{"log": ...}`, и
  `| json | level="ERROR"` не работал.
- cAdvisor в Docker Desktop отдаёт метрики на уровне пода без метки `container`, поэтому в
  запросах используется фильтр только по `pod`.
- Запросы дашборда исправлены: пример `| logfmt | count by (pod)` из задания не является
  корректным LogQL; использовано `sum by (pod) (count_over_time(... | json | level="ERROR" [$__range]))`.
- Одна Grafana (из `loki-stack`) подключена и к Loki, и к Prometheus; отдельная Grafana из
  kube-prometheus-stack отключена.
- Loki 2.9 отправляет оповещения по API v1 Alertmanager, который удалён в новых версиях
  (`410 Gone`); включён `enable_alertmanager_v2: true`.

## Результаты по этапам

- **Этап 1.** JSON-логи в stdout, пример строки:
  `{"timestamp": "...", "level": "ERROR", "message": "Request completed", "method": "GET", "path": "/crash", "status_code": 500, "duration": 0.0006, ...}`.
- **Этап 2.** Loki, Promtail, Grafana в `logging`; Prometheus, Alertmanager в `monitoring`
  (`logs/kubectl-survey.log`).
- **Этап 3.** Логи доступны через `kubectl logs` и LogQL: `{app="fastapi-app"} | json | level="ERROR"`.
- **Этап 4.** Обследование кластера и подов: `logs/kubectl-survey.log` (включая `kubectl top`
  через metrics-server); метрики и запросы PromQL — `logs/incident-evidence.log`.
- **Этап 5.** Дашборд «Incident Investigation Dashboard» (8 панелей): топ ошибок по подам, шкала
  5xx, запросы и ошибки, последние логи ошибок, CPU, память, p95, объём логов.
- **Этап 6.** Нагрузка на `/cpu` и `/crash`, расследование — `INVESTIGATION.md`.
- **Задание 1.** Правило Loki: `sum(count_over_time({app="fastapi-app"} |= "ERROR" [1m])) > 5`.
  Оповещение дошло до Alertmanager и до приёмника (`logs/alert-webhook.log`). Приёмник — webhook в
  кластере. Факт доставки оповещения подтверждён логом приёмника.
- **Задание 2.** Панель «Запросы и ошибки» (Prometheus: запросы/с и 5xx/с) стоит над панелью
  «Последние логи ошибок» (Loki) на одном дашборде с общим временным окном: выделение интервала на
  графике синхронно меняет окно логов.
- **Задание 3.** Эндпоинт `/crash` (30% ошибок), расследование и отчёт — `INVESTIGATION.md`;
  измеренная доля ошибок 29,5%.

## Ответы на контрольные вопросы

1. **Структурированное логирование.** JSON-строки разбираются машиной без регулярных
   выражений: можно фильтровать и агрегировать по полям (`level`, `path`, `status_code`),
   связывать записи по идентификаторам, поля не зависят от языка и формата сообщения. В облаке
   много экземпляров сервиса, и неструктурированный текст не поддаётся надёжному поиску.
2. **LogQL.** `{app="fastapi-app"} | json | level="ERROR"` с диапазоном «последний час» в
   Grafana; для подсчёта — `sum(count_over_time({app="fastapi-app"} | json | level="ERROR" [1h]))`.
3. **Корреляция.** По общему времени и общим меткам (`app`, `pod`, `namespace`): находят пик
   метрики (рост 5xx), берут тот же интервал в логах и разбирают сообщения; в Grafana — общее
   временное окно, панели Prometheus и Loki на одном дашборде, ссылки Explore между источниками.
4. **ELK и Loki.** Elasticsearch индексирует полный текст каждой записи: мощный поиск и
   аналитика, но высокие требования к памяти и диску. Loki индексирует только метки, а текст
   хранит сжатыми блоками: дешевле и проще, хорошо сочетается с Prometheus и Grafana, но
   полнотекстовый поиск медленнее. Loki — для логов Kubernetes и метрик рядом; ELK — для
   сложного поиска и аналитики по логам.
5. **Сбор логов Kubernetes.** Контейнер пишет в stdout/stderr, а среда выполнения сохраняет
   вывод в файлы на узле: `/var/log/pods/<namespace>_<pod>_<uid>/<container>/*.log`
   (символьные ссылки в `/var/log/containers/`). Их читает `kubectl logs` и агенты вроде
   Promtail. При удалении пода или ротации файлов логи теряются, поэтому нужен центральный сбор.
6. **План расследования.** Обнаружение (оповещение, дашборд) → определение временного окна →
   метрики (что изменилось: CPU, память, ошибки, латентность) → логи за окно (причина, поды,
   эндпоинты) → проверка событий кластера (`kubectl get events`, изменения развёртываний) →
   гипотеза и проверка → устранение → отчёт и улучшение оповещений.
7. **Панели дашборда.** Запросы/с, доля ошибок 5xx, латентность (p95/p99), CPU и память по
   подам, перезапуски подов, объём логов и последние ошибки, статус оповещений.
8. **Алертинг.** Для метрик — правила Prometheus (PrometheusRule) и Alertmanager; для логов —
   правила Loki ruler по LogQL (`count_over_time(...) > N`); получатели — Telegram, email,
   Slack, webhook; важны пороги, длительность `for`, группировка и подавление дублей.
9. **Аудиторские логи Kubernetes.** Журнал запросов к API-серверу (кто, что, когда сделал).
   Включается флагами `kube-apiserver`: `--audit-policy-file` с политикой (уровни `None`,
   `Metadata`, `Request`, `RequestResponse`) и `--audit-log-path` (либо webhook-бэкенд);
   в управляемых кластерах — через настройки облачного провайдера.
