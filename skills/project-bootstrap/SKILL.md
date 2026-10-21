---
name: project-bootstrap
description: Поднять новый проект на ядре (репозитории, профиль, клоны, правила, доки, контуры, канарейки). Триггеры «новый проект», «подними проект», «старт проекта».
---

# project-bootstrap — запуск нового проекта

Источник истины — `HOWTO-new-project.md` в ядре. Здесь — рабочий порядок и проверки.

1. **Репозитории:** private `<project>-docs`, `<project>-agents`; public `<project>-api`, `<project>-app`.
   Первый коммит кода → ветка `develop` по умолчанию; защита `develop` (PR + обязательный чек CI,
   `restrictions: null`).
2. **Профиль слоя** `<project>-agents/project.env`: `AGENTS`, `LANES`, `AGENT_*`, `PORT_*`, репозитории,
   `DOCKER_*`, план, `AWAITING`, `TASK_LANE`; порты — свободные (скан `ss -ltn`), без пересечений.
3. **Клоны** `<root>/<project>/<дорожка>-<код>/{api,app,docs}` + `agents/`; в каждом `api/.env` —
   свой `COMPOSE_PROJECT_NAME`, порты, `APP_SECRET`.
4. **Развёртывание:** `./setup.sh --layer <слой>` → `--check` (дрейф 0).
5. **Доки-скелет** + витрины (`sprint_plan.py --write` собирает без ошибок).
6. **Контуры:** dev-стенд, стенд приёмки, БД боевых данных; изоляция (сеть/том, без `container_name`).
7. **Канарейки:** `/health` 200 · `make ci` OK · `./gradlew build` SUCCESSFUL · `check_meta` и
   `sprint_plan --check` без нарушений · `--check` = 0.
8. **Передача ПМ** — скилл `handover-pack`.
