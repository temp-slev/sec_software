# Лабораторная работа №2. SAST (Static Application Security Testing)

Студент: Рудометкин Станислав Владимирович, группа 22-к-кб1, вариант 19.

Объект анализа — FastAPI-приложение с эндпоинтами `/`, `/health`, `/cpu`, `/metrics`,
к которому добавлены уязвимые эндпоинты и модуль `app/utils.py` (задание 3).

| Папка | Содержимое |
|---|---|
| `vulnerable/` | исходная версия с уязвимостями и отчёты сканеров в `vulnerable/reports/` |
| `fastapi-app/` | исправленная версия, отчёты повторного сканирования в `reports/`, `.bandit`, конфигурации CI в `ci/`, `.pre-commit-config.yaml`, тесты |

## Запуск

```bash
pip install bandit safety semgrep pip-audit
cd vulnerable          # затем то же самое для fastapi-app
bandit -r ./app -f txt
bandit -r ./app -f json -o reports/bandit-report.json
bandit -r ./app -f txt --severity-level medium
bandit -r ./app -f html -o reports/bandit-report.html
safety check -r requirements.txt            # см. примечание ниже
pip-audit -r requirements.txt --strict
semgrep scan ./app --config p/default
semgrep scan ./app --config p/security-audit --json -o reports/semgrep-report.json
```

Примечание о Safety: `safety scan` в версии 3.x требует бесплатной регистрации
(`safety auth`), без неё сканирование не стартует. Поэтому использована команда
`safety check` (открытая база) и `pip-audit` как независимая проверка. Для
скриншота отчёта можно один раз выполнить `safety auth` и затем `safety scan`.

## Результаты до исправления (`vulnerable/`)

**Bandit:** 13 замечаний — 2 High, 6 Medium, 5 Low. **Safety:** 28 уязвимостей в 5
пакетах, **pip-audit:** 20 уязвимостей. **Semgrep (security-audit):** 6 находок.

| Инструмент | Уязвимость | Файл | Строка | Рекомендация |
|---|---|---|---|---|
| Bandit | B602 (High): `subprocess` с `shell=True`, инъекция команд в `/ping` | app/main.py | 50 | список аргументов без shell, валидация `host` |
| Bandit, Semgrep | B501 (High): `requests.get(verify=False)` | app/main.py | 56 | убрать `verify=False`, ограничить список хостов |
| Bandit | B113 (Medium): запрос без timeout | app/main.py | 56 | `timeout=5` |
| Bandit, Semgrep | B506 (Medium): `yaml.load` с небезопасным Loader | app/main.py | 63 | `yaml.safe_load` |
| Bandit, Semgrep | B301 (Medium): десериализация `pickle` | app/main.py | 72 | заменить на JSON |
| Bandit | B108 (Medium): небезопасный временный файл в `/tmp` | app/main.py | 16 | файл в каталоге приложения, не в общем `/tmp` |
| Bandit | B104 (Medium): `host="0.0.0.0"` | app/main.py | 78 | `127.0.0.1` по умолчанию, настройка через `APP_HOST` |
| Bandit, Semgrep | B307 (Medium): `eval` на пользовательском вводе | app/utils.py | 2 | безопасный вычислитель на `ast` |
| Bandit | B105 (Low): пароль и токен в коде | app/main.py | 14, 15 | переменные окружения |
| Bandit | B101 (Low): `assert` в рабочем коде | app/main.py | 26 | удалить |
| Bandit | B403, B404 (Low): импорт `pickle`, `subprocess` | app/main.py | 2, 3 | убраны / обоснованы |
| Safety, pip-audit | старые версии fastapi 0.65.2, starlette 0.14.2, requests 2.25.1, PyYAML 5.3.1, Jinja2 2.11.2 | requirements.txt | — | обновить версии |

### Задание 1. HIGH-уровни Bandit

- `app/main.py:50` (B602): `subprocess.check_output("ping -c 1 " + host, shell=True)`.
  Исправление: `subprocess.run(["ping", "-c", "1", "--", host], timeout=5)` и проверка
  `host` как IP-адреса или имени по регулярному выражению.
- `app/main.py:56` (B501): `requests.get(url, verify=False)`. Исправление:
  `requests.get(url, timeout=5)` (проверка сертификата включена по умолчанию) и
  разрешённый список хостов против SSRF.

Файл `.bandit` исключает папки `tests` и `venv`.

### Задание 2. Анализ зависимостей

Safety нашёл по пакетам: starlette — 11, fastapi — 7, jinja2 — 5, requests — 4,
pyyaml — 1 (примеры: CVE-2024-22195, CVE-2024-34064, CVE-2024-56326,
CVE-2025-27516, CVE-2020-14343, CVE-2020-28493). Пути обновления:

| Пакет | Было | Стало |
|---|---|---|
| fastapi | 0.65.2 | 0.162.0 |
| starlette | 0.14.2 | 1.9.0 |
| requests | 2.25.1 | 2.34.2 |
| PyYAML | 5.3.1 | 6.0.3 |
| Jinja2 | 2.11.2 | 3.1.6 |
| uvicorn, psutil | 0.13.4, 5.8.0 | 0.54.0, 7.2.2 |

### Задание 3. eval → безопасный метод

`app/utils.py` с `eval` Bandit отмечает как B307. Исправление: функция `calculate`
разбирает выражение через `ast.parse` и разрешает только числа и арифметические
операции (`+ - * / ** %`), длина выражения и показатель степени ограничены.
`ast.literal_eval` для выражений вида `2 + 3` не подходит, он разбирает только
литералы, поэтому использован собственный вычислитель на `ast`. Тесты в
`fastapi-app/tests/test_app.py` проверяют, что инъекция `__import__('os').system('id')`
отклоняется.

## Результаты после исправления (`fastapi-app/`)

| Проверка | Результат |
|---|---|
| Bandit | 0 замечаний |
| Semgrep (p/default, p/security-audit) | 0 находок |
| Safety | 0 уязвимостей |
| pip-audit | No known vulnerabilities found |
| pytest | 7 тестов проходят |

Для `subprocess` в `/ping` оставлены комментарии `# nosec` с обоснованием: аргументы
передаются списком без shell, а `host` проверяется до вызова. Это пример ложного
срабатывания (вопрос 5).

## Интеграция в CI/CD (этап 6)

- pre-commit: `fastapi-app/.pre-commit-config.yaml` (хук Bandit).
- GitLab CI: `fastapi-app/ci/gitlab-ci.yml` (Bandit, Safety, pip-audit, Semgrep).
- GitHub Actions: `fastapi-app/ci/github-actions-sast.yml`.

## Ответы на контрольные вопросы

1. **SAST и DAST.** SAST анализирует исходный код и зависимости без запуска приложения
   и находит ошибки на ранних этапах; DAST проверяет работающее приложение «снаружи»
   (запросы, фаззинг) и видит проблемы конфигурации и окружения.
2. **Bandit.** Находит небезопасные вызовы (`eval`, `exec`, `pickle`, `shell=True`),
   слабую криптографию, хардкод паролей, отключённую проверку SSL, SQL-инъекции, слабые
   права на файлы. В CI запускается командой `bandit -r app -ll` с ненулевым кодом
   возврата при находках, также как pre-commit хук.
3. **Safety.** Сравнивает версии зависимостей с базой известных уязвимостей (CVE).
   Сканировать надо и зависимости, потому что значительная часть кода приложения —
   чужие библиотеки, а уязвимость в них эксплуатируется так же, как в собственном коде.
4. **Semgrep.** Работает по шаблонам, учитывающим структуру кода и поток данных, имеет
   правила для конкретных фреймворков и поддерживает много языков; правила легко писать
   самому. Фреймворк-специфичный анализ знает, какие функции FastAPI/Starlette получают
   пользовательские данные (источники) и какие вызовы опасны (стоки).
5. **Ложные срабатывания.** Разбираются вручную, подавляются точечно (`# nosec B603`
   с комментарием, `# nosemgrep`), исключаются в конфигурации (`.bandit`: `skips`,
   `exclude_dirs`) или базовой линией. Пример: `subprocess` без shell и с валидированным
   аргументом.
6. **OWASP Top 10.** A03 Injection (`eval`, shell, SQL), A02 Cryptographic Failures
   (хардкод секретов, слабые хеши), A08 Software and Data Integrity Failures (pickle,
   `yaml.load`), A06 Vulnerable and Outdated Components (Safety/pip-audit), A05 Security
   Misconfiguration (`0.0.0.0`, отключённая проверка SSL), A10 SSRF (запросы по
   пользовательскому URL).
