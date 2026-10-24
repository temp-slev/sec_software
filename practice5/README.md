# Практическое занятие №5. Автоматический QA (pytest, линтеры, форматеры)

Студент: Рудометкин Станислав Владимирович, группа 22-к-кб1, вариант 19.

Проект `qa_demo/`: FastAPI-приложение, тесты pytest, форматирование black и isort,
линтер flake8, хуки pre-commit и отчёт о покрытии.

## Запуск

```bash
cd qa_demo
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest                                   # 10 тестов
pytest --cov=src --cov-report=html       # отчёт в htmlcov/index.html
git init && pre-commit install           # хуки для локального репозитория
pre-commit run --all-files
```

## Состав

| Файл | Назначение |
|---|---|
| `qa_demo/src/main.py` | приложение: `GET /`, `POST /items/`, `GET /items/{name}`, `GET /items/`, `DELETE /items/{name}` |
| `qa_demo/tests/test_main.py` | тесты (10 запусков) |
| `qa_demo/tests/sample_item.json` | JSON-файл для проверки хука `check-json` |
| `qa_demo/pyproject.toml` | настройки black, isort, pytest |
| `qa_demo/.flake8` | настройки flake8 |
| `qa_demo/.pre-commit-config.yaml` | хуки: end-of-file-fixer, trailing-whitespace, check-added-large-files, check-json, black, isort, flake8 |
| `logs/` | протоколы реальных запусков |

## Ход работы и результаты

- **Тесты.** `logs/pytest.log`: 10 тестов проходят. В тестах добавлена фикстура,
  которая очищает хранилище перед каждым тестом, поэтому тесты не зависят от порядка
  запуска (в исходном листинге `test_get_item` рассчитывал на данные предыдущего теста).
- **Нарушение форматирования** (`logs/precommit-2.log`). В `src/main.py` намеренно
  добавлены лишние пробелы, неверные отступы и неотсортированные импорты. flake8
  показал ошибки E231, E201, E111, E117, W291, F401; black переформатировал файл, isort
  отсортировал импорты. Оставшуюся ошибку F401 (неиспользуемый `import os`) автоматически
  исправить нельзя, её удалили вручную.
- **Коммит.** `git commit` запускает все хуки автоматически; после исправления все
  семь хуков прошли (`logs/precommit-2.log`).
- **Покрытие** (`logs/coverage.log`): 100% (29 из 29 строк `src/main.py`).
- **Задание 1.** Добавлен `DELETE /items/{name}` и два теста (успешное удаление, удаление
  несуществующего товара).
- **Задание 2.** Хук `check-json` добавлен; isort уже был в конфигурации. Все хуки
  выполняются командой `pre-commit run --all-files`.
- **Задание 3.** `test_create_item` параметризован через `@pytest.mark.parametrize`
  тремя наборами данных, pytest запускает его три раза (`test_create_item[item_data0..2]`).

## Ответы на контрольные вопросы

1. **Запуск отдельных тестов.** `pytest tests/test_main.py::test_root` — один тест;
   `pytest tests/test_main.py` — файл; `pytest -k "item and not delete"` — по выражению
   в имени; `pytest -m имя_маркера` — по маркеру.
2. **TestClient.** Вызывает приложение напрямую, без запуска сервера и сети: тесты
   быстрые, стабильные, не требуют свободного порта, видят исключения приложения и
   позволяют подменять зависимости (`app.dependency_overrides`).
3. **Black и flake8.** Black — форматтер: сам переписывает код в единый стиль. Flake8 —
   линтер: ничего не меняет, а сообщает о нарушениях PEP 8 и об ошибках вроде
   неиспользуемых переменных и импортов. Вместе они дают единый стиль и находят
   проблемы, которые форматтер исправить не может.
4. **pre-commit.** Устанавливает Git-хук `pre-commit`, который перед каждым коммитом
   запускает настроенные проверки на изменённых файлах. Если хук что-то исправил или нашёл
   ошибку, коммит прерывается. Плохой код не попадает в историю, а проверки не зависят от
   дисциплины разработчика.
5. **Покрытие.** Доля строк (или веток) кода, выполненных тестами. 100% не гарантирует
   качества: строка может выполняться без проверки результата, не покрыты сочетания
   входных данных, граничные случаи и интеграции.
6. **pyproject.toml.** Это единый стандартизованный файл конфигурации (PEP 518/621) для
   инструментов и сборки: меньше разрозненных файлов, один формат, поддержка в pip и во
   всех современных инструментах. Flake8 пока читает только свои файлы, поэтому
   остаётся `.flake8`.
7. **CI/CD.** В GitHub Actions: шаги `actions/checkout`, `setup-python`, установка
   зависимостей, затем `pre-commit run --all-files` (или отдельно `black --check .`,
   `isort --check .`, `flake8`) и `pytest --cov`. Падение любого шага блокирует слияние.

```yaml
name: QA
on: [push, pull_request]
jobs:
  qa:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install -r requirements.txt
      - run: pre-commit run --all-files
      - run: pytest --cov=src
```
