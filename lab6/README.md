# Лабораторная работа №5 (файл «Лаба 6»). Пентест облачных систем (Kubernetes + FastAPI + Prometheus + Grafana)

Студенты: Рудометкин Станислав Владимирович, Татенко Мария Станиславовна, группа 22-к-кб1, вариант 19.

Легальное тестирование собственной учебной инфраструктуры: кластер Kubernetes из Docker
Desktop (развёрнут в Лабе 5), FastAPI-приложение в нём, а также сервисы из Практики 3 и
Лабы 4, запущенные локально для проверки уязвимостей веб-уровня.

## Состав

| Путь | Назначение |
|---|---|
| `k8s-kube-bench-job.yaml` | официальный манифест kube-bench (скачан и проверен перед применением) |
| `reports/` | JSON-отчёты kube-hunter, Kubescape (nsa, mitre, scan image) |
| `logs/` | протоколы всех команд по этапам 1–5 |
| `FINDINGS.md` | матрица уязвимостей, оценка цепочки атак (этап 6) |

## Инструменты

```bash
pip install kube-hunter
brew install kubescape
kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job.yaml
```

## Этап 1. Разведка

`logs/01-recon-network.log`, `logs/02-manual-recon.log`. API-сервер Kubernetes отвечает на
`localhost:6443`, но анонимный доступ запрещён (`403 Forbidden` на `/api` и
`/api/v1/namespaces`); `/version` отдаёт версию без авторизации (используется
kube-hunter'ом как находка). Порты kubelet (10250/10255) с хоста недоступны — Docker
Desktop публикует их только на внутреннем адресе ноды, а не на `localhost`.
kube-hunter (`reports/kube-hunter-report.json`) нашёл одну уязвимость: **K8s Version
Disclosure** (High, KHV002) — версия кластера видна через `/version`.

## Этап 2. Конфигурации и соответствие стандартам

- **kube-bench** (CIS Benchmark): `logs/03-kube-bench.log` — **62 PASS, 12 FAIL, 57 WARN**.
  Основные провалы: не включён audit log API-сервера (1.2.16–1.2.19), не выставлен
  `--profiling=false` на API Server/Controller Manager/Scheduler, не указан
  `--kubelet-certificate-authority` (1.2.5), владелец каталога etcd не `etcd:etcd` (1.1.12) —
  в Docker Desktop control plane управляется средой разработки, не производственным
  дистрибутивом, поэтому часть проверок ожидаемо не проходит.
- **Kubescape**: framework NSA — compliance 53% (`logs/06-kubescape-nsa.log`,
  `reports/kubescape-nsa-report.json`), framework MITRE ATT&CK — compliance 60%
  (`logs/07-kubescape-mitre.log`, `reports/kubescape-mitre-report.json`). Главные
  проблемы: 0% по NetworkPolicy (Ingress/Egress blocked), 74% по автомонтированию токена
  сервисного аккаунта, не включено шифрование etcd/секретов.
- **Pod Security.** `logs/08-pod-security.log`: у `fastapi-app` `securityContext` пуст (в
  отличие от системных подов мониторинга, у которых заданы `allowPrivilegeEscalation:
  false`, `capabilities.drop: [ALL]`, `readOnlyRootFilesystem: true`). Исправлено в
  `lab5/k8s/fastapi-app.yaml`, подробности — там же в README.

## Этап 3. RBAC и привилегии

`logs/04-rbac.log`, `logs/05-default-sa-check.log`. Текущий пользователь kubectl —
`system:masters` (admin-конфиг Docker Desktop), имеет полный доступ (`can-i '*' '*'` →
`yes`). `default` ServiceAccount в namespace `default` отдельных привязок ролей не имеет:
единственная подходящая привязка — `system:public-info-viewer` на группы
`system:authenticated`/`system:unauthenticated`, дающая доступ только к публичным
discovery-эндпоинтам. Проверено через имперсонацию (`kubectl --as=...` → `Forbidden` на
`get pods`); методическая деталь о ложном результате через `--token` — в `FINDINGS.md`.

## Этап 4. Безопасность FastAPI-приложений

`logs/09-fastapi-openapi.log` – `logs/11-idor-content-type-cors.log`. Цели: JWT-сервис
(Лаба 4, `localhost:8030`) и User Service (Практика 3, `localhost:8100`).

| Проверка | Результат |
|---|---|
| `/openapi.json`, `/docs`, `/redoc` | все эндпоинты из кода видны в схеме, скрытых (`include_in_schema=False`) нет |
| JWT: `alg=none` | отклонён, `401 Could not validate credentials` — `jwt.decode(..., algorithms=[ALGORITHM])` задан явно |
| JWT: состав токена | заголовок `HS256`, в payload есть `exp`; `iss`/`aud` не используются (одна доверенная аудитория — сам сервис) |
| IDOR на `PUT /users/{id}` (User Service) | **уязвимость подтверждена**: сторонний пользователь изменил чужую запись (id=2), владелец ресурса не проверяется |
| Content-Type switching | `application/x-www-form-urlencoded` и `multipart/form-data` отклонены `422` — Pydantic принимает только JSON |
| CORS | недоверенный `Origin` не получает `Access-Control-Allow-Origin`; для разрешённого источника (JWT-сервис, `ALLOWED_ORIGINS`) заголовки корректны |

## Этап 5. Контейнеры и попытка эскалации

`logs/12-container-escape-analysis.log`. Вместо запуска инструментов пост-эксплуатации
(CDK/Ckyn, предполагающих уже полученный RCE) проверены статические и рантайм-признаки
возможности побега:

- `securityContext` пода — пуст (см. этап 2).
- `hostPID`, `hostNetwork`, `hostIPC` — не заданы (по умолчанию `false`).
- Примонтированных томов, кроме стандартного `kube-api-access`, нет — `/var/run/docker.sock`
  не проброшен.
- Внутри контейнера: `id` → `uid=10001(appuser)`, не root; `/var/run/docker.sock`
  недоступен; эффективные capabilities (`CapEff`) — `0000000000000000`.

Вывод: условий для побега на хост нет. Это не отменяет рекомендацию явно задать
`securityContext` (сделано, см. Лабу 5) — сейчас защита держится на `USER` в Dockerfile,
а не на политике Kubernetes, и при изменении образа может быть потеряна незаметно.

## Этап 6 и задания

- Матрица уязвимостей, оценка цепочки атак, методическое замечание — `FINDINGS.md`.
- **Задание 1** (ручная проверка Secrets) — выполнено в рамках этапа 3
  (`logs/05-default-sa-check.log`): получен список секретов `default`, через
  `kubectl create token` и имперсонацию проверены права `default` ServiceAccount.
- **Задание 2** (IDOR) — выполнено в рамках этапа 4 (`logs/11-idor-content-type-cors.log`):
  два ресурса, доступ к чужому через смену `id`, уязвимость подтверждена и описана в
  `FINDINGS.md`.
- **Задание 3** (сканирование образа) — `kubescape scan image fastapi-logging:latest`:
  **172 уязвимости (0 Critical, 55 High)**, все — в системных пакетах базового образа
  `python:3.12-slim` (`util-linux`, `perl-base`, `zlib1g`, `libc6` и др.), ни одна не
  относится к самим Python-пакетам (`fastapi`, `uvicorn`, `starlette`). Снижение риска:
  регулярно пересобирать образ на свежий базовый слой, использовать более узкий базовый
  образ (`python:3.12-slim-bookworm`, `distroless`), сканировать образы в CI (как в
  `lab2/fastapi-app/ci/`) и отслеживать CVE через `pip-audit`/Kubescape на каждый релиз.

## Ответы на контрольные вопросы

1. **Ключевые порты.** API Server (6443) — управление всем кластером, при анонимном
   доступе или слабой авторизации даёт полный контроль. etcd (2379) — хранит все объекты
   кластера, включая Secrets в открытом виде (если нет encryption at rest); доступ к нему
   равносилен доступу ко всем секретам. kubelet (10250/10255) — управляет подами на узле;
   при открытом read-only API (10255) или без аутентификации на 10250 позволяет читать
   логи, выполнять команды в контейнерах и получать токены сервисных аккаунтов с узла.
2. **Опасные verb'ы RBAC.** `bind` — позволяет привязать роль с более широкими правами,
   чем есть у самого пользователя, к любому субъекту. `escalate` — разрешает менять
   ClusterRole/Role, в том числе собственную, расширяя права. `impersonate` — позволяет
   выполнять запросы от имени другого пользователя или ServiceAccount, в том числе с
   правами cluster-admin. Все три дают путь к повышению привилегий без прямого
   предоставления admin-прав.
3. **Признаки побега из контейнера.** Привилегированный режим (`privileged: true`) —
   снимает почти все ограничения ядра; capability `SYS_ADMIN` — даёт доступ к монтированию
   и многим системным операциям; `CAP_DAC_READ_SEARCH` — обходит проверку прав на чтение
   файлов; смонтированный `/var/run/docker.sock` или `hostPID`/`hostNetwork`/`hostIPC` —
   даёт видимость и влияние на процессы и сеть хоста или доступ к Docker Engine напрямую.
4. **Риски `/openapi.json` и `/docs` в production.** Раскрывают полную карту API: все
   эндпоинты, параметры, модели данных и форматы ошибок, облегчая разведку перед атакой;
   могут показывать внутренние/административные маршруты. Защита: отключать
   (`docs_url=None`, `openapi_url=None`) или закрывать аутентификацией/сетевым периметром
   в production, не полагаться на `include_in_schema=False` как на единственную защиту
   (эндпоинт всё равно доступен и работает, просто не виден в схеме).
5. **Алгоритмическая путаница в JWT.** Атака, когда сервер проверяет токен без явного
   ограничения алгоритма: токен, подписанный `alg=none`, принимается без проверки подписи,
   либо токен, подписанный открытым RSA-ключом как HMAC-секретом (RS256 → HS256), проходит
   проверку, потому что открытый ключ известен атакующему. Предотвращение: всегда
   передавать явный список разрешённых алгоритмов в `jwt.decode(..., algorithms=[...])` и
   никогда не выводить его из заголовка токена — как сделано в `app/auth.py` Лабы 4,
   что подтверждено тестом (`alg=none` отклонён).
6. **Цепочки уязвимостей.** Отдельная уязвимость часто ограничена контекстом (например,
   IDOR даёт доступ только к данным приложения, а не к инфраструктуре), но в сочетании с
   другой слабостью открывает следующий шаг: пример из занятия — SSRF в приложении
   позволяет обратиться к облачному metadata-сервису, оттуда получить временные IAM-
   учётные данные, с ними прочитать S3-бакет с `kubeconfig`, а с `kubeconfig` — получить
   полный доступ к кластеру. Каждый шаг по отдельности не критичен, но вместе они образуют
   путь от веб-уязвимости до полной компрометации инфраструктуры.
