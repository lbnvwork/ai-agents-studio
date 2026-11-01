# Команды в терминале (рабочий режим агента)

## Режим терминала — обязательная настройка

Cline → **Settings → Terminal → Terminal Execution Mode = «Background Exec»** (не «VS Code Terminal»).
В режиме «VS Code Terminal» вывод команд склеивается, коды возврата врут, длинные команды обрезаются.
**Симптом:** «Shell integration did not report command completion … timing heuristic» или вывод не соответствует команде.
Диагностика и лечение — скилл `terminal-recovery`.

## Канарейки (30 секунд)

```bash
echo "canary ok"                                   # должен вернуться своим выводом
sleep 8; echo "long ok"                            # длинная команда — тоже
docker compose exec -T <сервис> sh -lc '<команда тестов>'   # реальная длинная (команды — в скилле run-tests)
```

Все три вернулись своими выводами — режим в порядке.

## Docker: `-p` обычно не нужен

В каталоге может быть несколько compose-проектов, но проект берётся из `COMPOSE_PROJECT_NAME` в `.env` клона,
поэтому команда одинаково работает у любого агента. Явный `-p` — только чтобы адресовать **чужой** проект из этого каталога.
Имя своего проекта — в `.clinerules/00-role.md` или в `docker compose ls`.

```bash
docker compose ls                                                             # какие проекты подняты и откуда
docker compose exec -T php sh -lc 'vendor/bin/phpunit'                        # пример веб-стека: backend
docker compose exec -T node sh -lc 'npm test'                                 # пример веб-стека: frontend, /app
docker compose exec -T php sh -lc 'php bin/console cache:clear'                # после обновления кода без rebuild
```

Свои команды (стек проекта) — в скилле `run-tests`.

## Гигиена команд

- Неинтерактивно: `-T` для `docker exec`/`run`, `--no-pager` для git, `-y` / `--no-input` для пакетных менеджеров. В Background Exec терминал невидим: команда, ждущая ввода, повиснет молча.
- Одна команда = одно действие — читаемый дифф и отчёт. Пачка команд в одном вызове допустима только для быстрых независимых проверок.
- Не создавай ложных падений: `… || true`, `; echo "exit=$?"` — чтобы «нет совпадений» в `grep` не выглядело как ошибка.
- Локальный рантайм годится только для мелочей: сборка и тесты — в контейнере (локальная версия рантайма легко расходится с образом проекта).
- **Команды не запускаются / `spawn /usr/bin/bash ENOENT`** — это мёртвый `cwd`, а не bash: скилл `terminal-recovery`.

