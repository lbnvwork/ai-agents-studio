---
name: check-coverage
description: Покрытие тестами — где смотреть и как прогонять (frontend vitest/v8, backend PHPUnit+Xdebug), что считать блокером; цель — 100% по изменённым файлам.
---

# Покрытие: чем проверять и что требовать

**Когда:** деф — последним шагом перед PR; ревьюер — при ревью. **Цель — 100% по изменённым
файлам**; общий процент модуля вторичен.

## Frontend (vitest + v8) — настроенный контур

```bash
cd frontend
npm run test:coverage              # vitest run --coverage → coverage/coverage-summary.json
node scripts/coverage-report.mjs   # факт и порог рядом; код 1 — отчёта нет
```

- пороги — `frontend/coverage-thresholds.json`: **единый источник**, его читают и гейт
  (`frontend/vitest.config.js`), и отчёт;
- свои файлы ищем в `coverage/coverage-summary.json` по путям из
  `git diff --name-only origin/develop...`;
- в CI это шаги `fe-coverage` и `fe-coverage-report` (`make ci`), отчёт — в артефактах прогона.

## Backend (PHPUnit + Xdebug) — отчёт руками

Автопорогов нет, Xdebug в контейнере есть (PHPUnit 12):

```bash
# сводка: по классам — Methods / Lines
docker compose exec -T php sh -lc 'XDEBUG_MODE=coverage vendor/bin/phpunit \
  --coverage-text --colors=never'

# только изменённый контекст — быстрее
docker compose exec -T php sh -lc 'XDEBUG_MODE=coverage vendor/bin/phpunit \
  --coverage-filter src/Ibs/Context/<Context> --coverage-text --colors=never'

# машинный отчёт: методы с count="0" — непокрытые
docker compose exec -T php sh -lc 'mkdir -p var/coverage && XDEBUG_MODE=coverage \
  vendor/bin/phpunit --coverage-clover var/coverage/clover.xml'
grep -B2 'count="0"' api/var/coverage/clover.xml
```

`0%` или пустой отчёт — не выставлен `XDEBUG_MODE=coverage`, неверный `--coverage-filter`
или тесты не дошли до кода; это диагноз, а не «кода нет».

## Что пишем в PR

- Изменённые строки и функции покрыты; новых методов с `count="0"` нет.
- Одна строка итога: `покрытие (изменённые файлы): <модуль/файл> lines X%, functions Y%;
  непокрыто: <список или «нет»>`.
- Покрыть нельзя — обоснование (что мешает) и предложение по тесту; ревьюер решает:
  блокер или долг.
- Красный гейт (`fe-coverage` / `fe-coverage-report`) — блокер, не долг.

## Чего не делаем

- Не поднимаем процент тестами без ассертов и «вызовами ради строки».
- Не исключаем файл из покрытия ради порога без записанной причины.
- Не считаем «покрыто», если тест есть, но ветка в нём не проверена.

## Для аквариума

Отчёт покрытия — **источник истины для негативных веток**: прогоняем по файлам блоков
(`--coverage-filter`) и в «Негативные ветки» пишем тест для покрытого сценария; непокрытое
(`count="0"`) помечаем как «теста нет — стоит добавить». Так ветки не теряются и не выдумываются.
