# Практическое занятие №1. Git: ветвление, слияние, удалённый репозиторий

Студент: Рудометкин Станислав Владимирович, группа 22-к-кб1, вариант 19.

## Что сделано

Выполнены все этапы 1–6 и задания 1–3 раздела 4. Работа велась в отдельном
репозитории `project_name` (с удалённым `origin`, ветка `main`). В этой папке лежит
итоговое состояние проекта (`project_name/`) и история коммитов (`git-log.txt`).

Последовательность действий:

1. `git clone <url> && cd project_name` — клонирование пустого репозитория.
2. Созданы `main.py`, `README.md`, `docs/info.txt`; коммит
   `feat: initial project structure added`.
3. `git checkout -b feature/add_greeting`; `main()` принимает `name`, вызов
   `main("Student")`; коммит `feat: add personalized greeting function`.
4. `git checkout main`, `git merge feature/add_greeting` (fast-forward),
   `git branch -d feature/add_greeting`.
5. `git pull origin main`, `git push origin main`.
6. Конфликт: ветка `hotfix/readme_update` (`# Super Project v2.0`) и `main`
   (`# Super Project v1.9`) изменили одну строку. При `git merge` возник конфликт в
   `README.md`:

   ```
   <<<<<<< HEAD
   # Super Project v1.9
   =======
   # Super Project v2.0
   >>>>>>> hotfix/readme_update
   ```

   Маркеры удалены, оставлен `# Super Project v2.0`, затем
   `git add README.md` и `git commit -m "merge: resolve conflict in README"`.
7. Задание 1: ветка `feature/config`, файл `config.ini`, коммит
   `chore: add config file`, слияние `git merge --no-ff feature/config`,
   удаление ветки.
8. Задание 2: `git log --oneline --graph --all`.
9. Задание 3: `git push origin main`.

## История коммитов (задание 2)

```
*   4bda6f8 Merge branch 'feature/config'
|\
| * 596e663 chore: add config file
|/
*   0d3fdbd merge: resolve conflict in README
|\
| * 3485a42 docs: update title
* | cf76d6f docs: fix version
|/
* e4d4e8d feat: add personalized greeting function
* c60bf98 feat: initial project structure added
```

Хеши первых трёх коммитов (в хронологическом порядке): `c60bf98`, `e4d4e8d`, `3485a42`.
Три верхних коммита графа (самые новые): `4bda6f8`, `596e663`, `0d3fdbd`.
Хеши в вашем репозитории будут другими: они зависят от даты и автора.

## Ответы на контрольные вопросы

1. **merge и rebase.** `merge` объединяет две ветки, создавая новый коммит слияния и
   сохраняя историю как есть. `rebase` переносит коммиты одной ветки поверх другой,
   переписывая их, и история получается линейной.
2. **`--no-ff`.** Опция всегда создаёт коммит слияния, даже если возможен
   fast-forward. В истории остаётся видно, что была отдельная ветка с фичей и какие
   коммиты в неё входили. Без опции указатель `main` просто сдвинется вперёд, и
   следов ветки не останется.
3. **`rejected (non-fast-forward)`.** Значит, на сервере есть коммиты, которых нет
   локально. Алгоритм: `git pull origin main` (или `git fetch` и затем `git rebase
   origin/main`), при конфликтах исправить файлы, `git add`, завершить слияние
   или rebase, проверить результат и повторить `git push origin main`. Принудительный
   `push --force` использовать нельзя: он затрёт чужие коммиты.
4. **Индекс (staging area).** Это область между рабочей директорией и репозиторием, в
   которой собирается содержимое следующего коммита. `git add` нужен и для уже
   отслеживаемых файлов: коммит включает только то, что добавлено в индекс, поэтому
   можно сделать несколько небольших логичных коммитов из набора правок.
5. **Отмена изменений в рабочей директории.** `git restore <файл>` (в старых версиях
   `git checkout -- <файл>`); для всех файлов `git restore .`.
6. **Изменённые, но не добавленные файлы.** `git status`; сами изменения показывает
   `git diff`, а список имён — `git diff --name-only`.
