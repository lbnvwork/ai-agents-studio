#!/usr/bin/env bash
# pre-push для клонов студийных агентов: push разрешён только руководителю.
# Агент пушит только при явном ALLOW_PUSH=1 (так делает руководитель).
if [ "${ALLOW_PUSH:-0}" = "1" ]; then
  exit 0
fi
echo "  ⛔ push из клона студийного агента запрещён." >&2
echo "     Руководитель: ALLOW_PUSH=1 git push origin <ветка>." >&2
exit 1
