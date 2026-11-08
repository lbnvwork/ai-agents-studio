#!/bin/sh
# pre-commit для клонов проектных доков, где пишет студийный агент.
# Разрешает коммит только путей из его раздела. Остальное — руководитель.
# Установка: cp toolkit/hooks/pre-commit-own-section.sh <клон>/.git/hooks/pre-commit && chmod +x
# Разовая миграция каталогов: git commit --no-verify (только руководитель).

ALLOW="${OWN_SECTION:-([0-9]+-)?(Юридическое|Безопасность|Клиническое)}"

# ACМRTD: добавления, изменения, переименования, удаления — всё проверяем
list=$(git -c core.quotepath=false diff --cached --name-only --diff-filter=ACMRTD)
bad=$(printf '%s\n' "$list" | grep -vE "(^|/)${ALLOW}/" | grep -v '^$')

if [ -n "$bad" ]; then
  echo "КОММИТ ОТКЛОНЁН: разрешён только свой раздел ($ALLOW)." >&2
  echo "Вне раздела:" >&2
  printf '  %s\n' "$bad" >&2
  echo "Всё остальное коммитит руководитель. Разовая миграция каталогов — git commit --no-verify." >&2
  exit 1
fi
exit 0
