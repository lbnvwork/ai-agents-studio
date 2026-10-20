# Как поднять новый проект на ядре (за час)

Пошаговый рецепт. Проверено на двух проектах (ibs, MedDrive). Все команды — с подстановкой своих значений.

## 0. Что где живёт

| Слой | Что это | Видимость |
|---|---|---|
| **Ядро** `ai-agents-studio` | правила, роли, скиллы, toolkit, шаблоны, `setup.sh` | public |
| **Проектный слой** `<project>-agents` | `project.env`, свои скиллы/карточки, шаблоны задач | private |
| **Доки** `<project>-docs` | Obsidian-хранилище: план, статьи, регламенты, витрины | private |
| **Код** `<project>-api`, `<project>-app` | репозитории треков | public |
| **Клоны агентов** `~/…/<project>/<дорожка>-<код>` | воркспейс: `{api, app, docs}` + `.clinerules`, `.cline` | локально |

**Правило:** правила и toolkit правятся **только в ядре** (или в слое), клоны — сгенерированные копии.

## 1. Репозитории и защита веток

```bash
for r in <project>-api <project>-app; do gh repo create lbnvwork/$r --public  --description "…"; done
for r in <project>-docs <project>-agents; do gh repo create lbnvwork/$r --private --description "…"; done
```

После первого коммита в код — `develop` ветка по умолчанию и защита:

```bash
gh repo edit lbnvwork/<project>-api --default-branch develop
gh api -X PUT repos/lbnvwork/<project>-api/branches/develop/protection --input - <<'JSON'
{"required_status_checks": {"strict": true, "contexts": ["Backend (PHP 8.3)"]},
 "enforce_admins": false,
 "required_pull_request_reviews": {"required_approving_review_count": 0, "dismiss_stale_reviews": false},
 "restrictions": null, "allow_force_pushes": false, "allow_deletions": false}
JSON
```

`contexts` — имя джобы CI (`Backend (PHP 8.3)` / `Build (JDK 21)`). `restrictions: null` обязателен, иначе API вернёт 422.

## 2. Профиль слоя (`<project>-agents/project.env`)

Копируй `profiles/_template/project.env.dist` и заполни обязательное:

- **Идентификация:** `PROJECT`, `PROJECT_TITLE`, `PROJECT_KIND` (`web` / `mobile` / `api+mobile`).
- **Клоны:** `AGENTS_ROOT`, `AGENT_PREFIX` (если каталоги вида `<дорожка>-<код>`, ставь `*-` — тогда слой `agents/` не попадёт в glob'ы скиллов), `AGENTS="dir:код:дорожка …"`.
- **Дорожки:** `LANES="дорожка:ёмкость:название …"` (порядок = порядок в витринах).
- **Агенты:** `AGENT_TITLE_<КОД>`, `AGENT_SHORT_<КОД>`, `AGENT_DOES_<КОД>`, `AGENT_STEM_<КОД>`, `PORT_<СТЕМ>_{APP,DB,WEB}`.
- **Репозитории:** `CODE_REPO` / `CODE_REPO_URL` (основной), `APP_REPO` / `APP_REPO_URL` (если треков два), `DOCS_REPO*`, `PM_DIR`.
- **Docker:** `DOCKER_PREFIX`, `DOCKER_PM`, `DOCKER_DEV`, `DOCKER_PROD`, `DOCKER_PRODDATA`, `PROD_DATA_DIR`.
- **План:** `CUR_SPRINT`, `SPRINT_FROM`, `SPRINT_TO`, `MIN_PLAN_SPRINT`, `ARCHIVE_TO`, `SPRINT_DAYS`, `CAP_*`, `DEADLINE_D1/D2` (+ `*_NOTE`), `STAGES`, `HOURS_PER_DAY`, `ARCH_PERIOD`.
- **Процесс:** `AWAITING` (словарь: `значение:owner|lane:ref|agent:ref|none`), `OWNER_CODE/OWNER_TITLE`, `TASK_LANE` (тип задачи → дорожка).
- **Шаблон задачи:** `templates/task_stub.md` + `STUB_TZ_*`, `STUB_VERIFICATION`.

**Порты:** выбери свободный диапазон и проверь до старта:
```bash
for p in $(seq 8101 8116) $(seq 5532 5549); do ss -ltn "sport = :$p" | grep -q LISTEN && echo "занят $p"; done
```

**Значение `0` валидно** (проект может начинаться со спринта 0) — не заменяй его на пустое.

## 3. Клоны агентов и локальные `.env`

```bash
cd ~/work/<путь>/<project>
for d in pm-jan analyst-feb lead-apr dev-may dev-jun tester-mar devops-jul; do
  mkdir -p $d && git clone git@github.com:<org>/<project>-api.git $d/api
  git clone git@github.com:<org>/<project>-app.git $d/app           # если есть второй трек
  git clone git@github.com:<org>/<project>-docs.git $d/docs
done
git clone git@github.com:<org>/<project>-agents.git agents
```

В `<клон>/api/.env` (локально, gitignored): `APP_PORT`, `DB_PORT`, `POSTGRES_*`, `APP_SECRET`,
`COMPOSE_PROJECT_NAME=<prefix>_<стем>` — свой проект и порты у каждого агента.

## 4. Развёртывание правил и toolkit

```bash
cd <ядро>
./setup.sh --layer <путь>/<project>/agents            # развернуть
./setup.sh --layer <путь>/<project>/agents --check    # дрейф = 0
```

Что делает: раскладывает `.clinerules/`, `.cline/skills/`, конфиг `.agents` (`CORE`, `PROJECT`, `LAYER`)
и toolkit-скрипты в `docs/09-Служебное/Скрипты/` **каждого** клона. Глобальные скиллы — симлинки в ядро,
поэтому **плейсхолдеров в них быть не должно** (иначе агенты увидят сырое `{{…}}`).

## 5. Доки-скелет

Скопируй из проекта-образца механизмы (не данные): `00-Главная.md`, `03-Задачи/{Канбан.md,_Шаблоны/*}`,
`09-Служебное/{Дашборд руководителя.md,Регламенты/*}`, `03-Задачи/Планы спринтов/{Команда и ёмкость.md,Покрытие ТЗ (FUNC).md}`.
Затем подставь имена/порты и создай пустыми: `Спринт-01.md` (шапка с датами и ёмкостью), `Спринты/Спринт-01/`,
`09-Служебное/{Решения и риски,Команды,Ссылки,Выполненные работы}.md`, `02-Аналитика/{Техническое задание,FUNC-матрица,Глоссарий}.md`,
`.gitignore` (`.agents`, `__pycache__`, `.obsidian/`, доступы).

Проверка: `python3 09-Служебное/Скрипты/sprint_plan.py --write` → витрины собираются без ошибок;
дашборд показывает `SPRINTS / TEAM / SCOPE / ARCHIVE / FUNC: ok`.

## 6. Docker-контуры

| Контур | Проект | Назначение |
|---|---|---|
| стеки агентов | `<prefix>_<стем>` | локальная работа, свои порты |
| dev-стенд | `med_pm_dev` | общий для команды |
| стенд приёмки | `med_pm_prod` | приёмка руководителя, своя БД |
| БД боевых данных | `med_prod_data` | read-only копия боевой БД |

- Изоляция: своя сеть `<проект>_net`, свой том `<проект>_db_data`, **никаких `container_name`**.
- **Базовый compose — прод** (`composer install --no-dev`), dev-настройки — в `docker-compose.override.yml`
  (`composer install` с dev-пакетами, миграции). Иначе запуск стека стирает dev-пакеты из `vendor`.
- Секреты — только в локальных `.env` (chmod 600).

## 7. Канарейки (что должно быть зелёным)

| Проверка | Ожидаемо |
|---|---|
| `docker compose up -d --build` в `api/` | `db/php/nginx — running` |
| `curl localhost:<APP_PORT>/health` | `HTTP 200 {"status":"ok"}` |
| `make ci` (в контейнере или локально с dev-пакетом) | phpunit OK · phpstan OK · cs-fixer 0 · deptrac 0 |
| `./gradlew build` (трек app) | `BUILD SUCCESSFUL` |
| `python3 check_meta.py` в docs | «нарушений нет» |
| `python3 sprint_plan.py --check` | «нарушений нет», диапазон спринтов из профиля |
| `./setup.sh --layer … --check` | «Дрейфа нет» |
| `bash hooks/context-summary.sh` с `MEMORY_FILE=…` | валидный JSON `hookEventName: PreCompact` |

## 8. Сдача проекта

1. **Obsidian:** руководитель открывает `docs/` клона РП как хранилище.
2. **Хуки PreCompact** — по строке на воркспейс (см. §9).
3. **`.cline/context.md`** в каждом воркспейсе (5–10 строк: проект, треки, что дальше).
4. **Handover-доки:** `09-Служебное/Инструкции/Старт РП (<project>).md` + `Спринт-00 «реформа»` (подготовительные задачи).
5. **Промт новому ПМ:** `templates/pm-onboarding-prompt.md` — подставить значения и отправить.
6. **Коммиты** делает руководитель; агент присылает названия.

## 9. Хук PreCompact (на каждый воркспейс)

```bash
MEMORY_FILE=<путь>/<project>/<клон>/.cline/context.md bash <ядро>/hooks/context-summary.sh
```

Событие — только `PreCompact`. На `UserPromptSubmit`/`PostToolUse`/`TaskResume` не вешать (раздует контекст).

## 10. Чек-лист «готово»

- [ ] репозитории созданы, `develop` защищена, PR-шаблон на месте
- [ ] профиль слоя заполнен, порты свободны, `0` не «съеден»
- [ ] 7 клонов = `{api, app, docs}` + `.clinerules` + `.cline`, ветки верные
- [ ] `setup.sh --layer … --check` → дрейф 0
- [ ] витрины собираются (`sprint_plan --write`), дашборд заполняет все AUTO
- [ ] `check_meta` / `sprint_plan --check` / `check_comments` — без нарушений
- [ ] `make ci` и `./gradlew build` зелёные, `/health` отвечает
- [ ] контуры dev/приёмка/prod-data поднимаются и изолированы
- [ ] `.cline/context.md` + строка хука у каждого агента
- [ ] «Старт РП», Спринт-00, промт ПМ — на месте
- [ ] `templates/task_stub.md` в слое соответствует стеку
- [ ] всё запушено: `git status` чистый во всех репозиториях

## 11. Типовые грабли (из практики)

1. **Гонки при параллельных командах.** Установка и проверка в одном вызове дают ложный «дрейф/старое состояние». Ставь и проверяй **разными вызовами** (или последовательно через `&&`).
2. **`pull.rebase` в клонах доков.** Без него `git pull` спотыкается о divergent branches: `git config pull.rebase true` в каждом клоне `docs`.
3. **`AGENT_PREFIX` и раскладка.** Глобы скиллов (`{{AGENT_PREFIX}}*`) должны попадать только в клоны: если в корне лежит слой `agents/`, используй `*-`.
4. **Плейсхолдеры в глобальных скиллах.** Они разворачиваются симлинками → `{{…}}` виден агентам. Глобальные скиллы — проектно-нейтральные.
5. **Комментарии в значениях профиля.** `KEY=web  # comment` — парсер отрежет комментарий, но пиши его отдельной строкой для читаемости.
6. **`--no-dev` в базовом compose** стирает dev-пакеты; dev-режим — только через override.
7. **Копирование `vendor`** (если нет сети): копируй в пустой каталог (иначе вложится `vendor/vendor`), и помни про `composer.lock` content-hash при смене `name`.
8. **Клоны отстают от remote:** после пуша в репозиторий кода/доков обнови все 7 клонов, иначе у агентов нет новых файлов (`Makefile`, override, инструкции).
9. **Перенос задачи = новый код** целевого спринта + `carried_from` (см. регламент «План и данные»).
10. **Хардкоды в скриптах всплывают на новом проекте:** если витрина «не видит» данные (например спринт 0), проверь, что диапазоны/пороги берутся из профиля, а не из констант.

## 12. Приложение

- Промт новому ПМ: `templates/pm-onboarding-prompt.md`
- Профиль-образец: `profiles/_template/project.env.dist`, шаблон задачи: `profiles/_template/templates/task_stub.md`
- Toolkit: `toolkit/README.md` · Эталонные проекты: ibs (web, 7 агентов), MedDrive (api + mobile, два трека)
