#!/bin/sh
# pre-commit для клона проектных доков, где пишет Ной (безопасность).
# Разрешает: раздел Безопасность/** и статьи 03-Задачи/** (раздел «Безопасность» + канал Ноя).
# Всё остальное — руководитель. Установка:
#   cp toolkit/hooks/pre-commit-sec.sh <клон>/.git/hooks/pre-commit && chmod +x
# Разовая миграция каталогов: git commit --no-verify (только руководитель).

ALLOW="([0-9]+-)?(Безопасность)|03-Задачи"

list=$(git -c core.quotepath=false diff --cached --name-only --diff-filter=ACMRTD)
bad=$(printf '%s\n' "$list" | grep -vE "(^|/)(${ALLOW})/" | grep -v '^$')

if [ -n "$bad" ]; then
  echo "КОММИТ ОТКЛОНЁН: разрешены только раздел «Безопасность» и статьи 03-Задачи." >&2
  echo "Вне разрешённого:" >&2
  printf '  %s\n' "$bad" >&2
  echo "Остальное коммитит руководитель. Разовая миграция — git commit --no-verify." >&2
  exit 1
fi
exit 0
