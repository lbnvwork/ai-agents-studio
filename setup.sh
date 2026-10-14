#!/usr/bin/env bash
# Развёртывание настроек агентов (правила + скиллы) из ядра ai-agents-studio.
#
# Ядро нейтрально: в правилах/ролях/скиллах стоят плейсхолдеры {{KEY}}, значения
# берутся из профиля проекта profiles/<project>/project.env (в git не хранится).
# Само ядро имён проектов не знает.
#
# Запуск из корня ядра:
#   ./setup.sh                                     # единственный профиль — автоопределение
#   ./setup.sh --project <project>                 # выбрать проект явно
#   ./setup.sh --project <project> --only <префикс>dev-may   # точечно (пилот)
#   ./setup.sh --project <project> --root /path/to/projects  # другой корень клонов
#   ./setup.sh --project <project> --dry-run       # показать, что будет сделано
#   ./setup.sh --project <project> --check         # проверить дрейф копий (ничего не пишет)
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
PROJECT=""
DRY=0
CHECK=0
ONLY=""
ROOT_OVERRIDE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT="${2:-}"; shift ;;
    --root)    ROOT_OVERRIDE="${2:-}"; shift ;;
    --only)    ONLY="${2:-}"; shift ;;
    --dry-run) DRY=1 ;;
    --check)   CHECK=1; DRY=1 ;;
    -h|--help) awk 'NR==1{next} /^set -euo/{exit} {print}' "$0"; exit 0 ;;
  esac
  shift
done

# Проект: явно из --project; если не задан — автоопределение по единственному
# рабочему профилю (ядро имён не хардкодит). Несколько профилей → просим --project.
if [ -z "$PROJECT" ]; then
  PROJECTS=()
  for f in "$ROOT"/profiles/*/project.env; do
    [ -f "$f" ] || continue
    PROJECTS+=("$(basename "$(dirname "$f")")")
  done
  case "${#PROJECTS[@]}" in
    1) PROJECT="${PROJECTS[0]}"; echo "== Профиль не задан, использую единственный: $PROJECT ==" ;;
    0) echo "нет ни одного профиля: profiles/<project>/project.env"
       echo "создай: cp profiles/_template/project.env.dist profiles/<project>/project.env"
       exit 2 ;;
    *) echo "в profiles/ несколько проектов: ${PROJECTS[*]}"
       echo "укажи явно: ./setup.sh --project <имя>"
       exit 2 ;;
  esac
fi

PROFILE="$ROOT/profiles/$PROJECT/project.env"
if [ ! -f "$PROFILE" ]; then
  echo "нет профиля: $PROFILE"
  echo "скопируй шаблон: cp profiles/_template/project.env.dist profiles/$PROJECT/project.env"
  exit 2
fi
# shellcheck disable=SC1090
set -a; . "$PROFILE"; set +a
if [ -n "$ROOT_OVERRIDE" ]; then AGENTS_ROOT="$ROOT_OVERRIDE"; fi
AGENTS_DIR="$AGENTS_ROOT"

GLOBAL_SKILLS=(git-workflow sync-env write-instruction)
STALE_GLOBAL=(explain-db make-postman run-tests write-adr write-e2e-scenario)
declare -A ROLE_SKILLS=(
  [jan]="review-code status-briefing find-dead-code"
  [apr]="run-tests explain-db write-aquarium write-adr review-code find-dead-code"
  [feb]=""
  [may]="run-tests explain-db write-aquarium find-dead-code"
  [jun]="run-tests explain-db write-aquarium find-dead-code"
  [mar]="run-tests make-postman write-e2e-scenario"
  [jul]="run-tests release find-dead-code"
)
DRIFT=0

role_dir_suffix() {
  case "$1" in
    jan) echo "pm-jan" ;; feb) echo "analyst-feb" ;; apr) echo "lead-apr" ;;
    may) echo "dev-may" ;; jun) echo "dev-jun" ;; mar) echo "tester-mar" ;; jul) echo "devops-jul" ;;
    *) echo "$1" ;;
  esac
}

# Роль → стем docker-проекта и портов (DOCKER_PREFIX_<стем>, PORT_<СТЕМ>_APP|DB|WEB)
role_stem() {
  case "$1" in
    jan) echo "pm" ;; apr) echo "lead" ;; feb) echo "feb" ;;
    may) echo "may" ;; jun) echo "jun" ;; mar) echo "tester" ;; jul) echo "jul" ;;
    *) echo "$1" ;;
  esac
}

render() {
  local src="$1" role="$2" out ru app_ptr db_ptr web_ptr agent_dir stem
  local pairs pair key val
  out="$(cat "$src")"
  stem="$(role_stem "$role")"
  ru="$(echo "$stem" | tr '[:lower:]' '[:upper:]')"
  agent_dir="$AGENTS_DIR/${AGENT_PREFIX}$(role_dir_suffix "$role")"
  app_ptr="PORT_${ru}_APP"; db_ptr="PORT_${ru}_DB"; web_ptr="PORT_${ru}_WEB"
  pairs=(
    "{{AGENT_DIR}}=$agent_dir"
    "{{DOCKER_PROJECT}}=${DOCKER_PREFIX}_${stem}"
    "{{PORT_APP}}=${!app_ptr:-}" "{{PORT_DB}}=${!db_ptr:-}" "{{PORT_WEB}}=${!web_ptr:-}"
    "{{PROJECT}}=$PROJECT" "{{PROJECT_TITLE}}=${PROJECT_TITLE:-}"
    "{{AGENTS_ROOT}}=$AGENTS_ROOT" "{{AGENT_PREFIX}}=$AGENT_PREFIX"
    "{{CODE_REPO}}=$CODE_REPO" "{{CODE_REPO_URL}}=${CODE_REPO_URL:-}" "{{CODE_BRANCH}}=$CODE_BRANCH"
    "{{DOCS_REPO}}=$DOCS_REPO" "{{DOCS_REPO_URL}}=${DOCS_REPO_URL:-}" "{{DOCS_BRANCH}}=$DOCS_BRANCH"
    "{{PM_DIR}}=$PM_DIR" "{{DOCKER_PREFIX}}=$DOCKER_PREFIX" "{{DOCKER_PM}}=$DOCKER_PM"
    "{{DOCKER_DEV}}=$DOCKER_DEV" "{{DOCKER_PROD}}=$DOCKER_PROD" "{{PROD_DATA_DIR}}=$PROD_DATA_DIR"
    "{{PORT_DEV_APP}}=$PORT_DEV_APP" "{{PORT_DEV_DB}}=$PORT_DEV_DB" "{{PORT_DEV_WEB}}=$PORT_DEV_WEB"
    "{{PORT_PROD_APP}}=$PORT_PROD_APP" "{{PORT_PROD_DB}}=$PORT_PROD_DB"
    "{{CUR_SPRINT}}=$CUR_SPRINT" "{{SPRINT_FROM}}=$SPRINT_FROM" "{{SPRINT_TO}}=$SPRINT_TO"
    "{{DEADLINE_D1}}=${DEADLINE_D1:-}" "{{DEADLINE_D2}}=${DEADLINE_D2:-}"
    "{{SPRINT_DAYS}}=$SPRINT_DAYS" "{{CAP_DEV}}=$CAP_DEV" "{{CAP_LEAD}}=$CAP_LEAD"
    "{{CAP_ANALYTICS}}=$CAP_ANALYTICS" "{{CAP_TEST}}=$CAP_TEST" "{{CAP_DEVOPS}}=$CAP_DEVOPS" "{{CAP_PM}}=$CAP_PM"
  )
  for pair in "${pairs[@]}"; do
    key="${pair%%=*}"; val="${pair#*=}"
    out="${out//"$key"/$val}"
  done
  printf '%s\n' "$out"
}

ensure_file() {  # ensure_file <содержимое> <путь>
  local content="$1" path="$2"
  if [ "$CHECK" = 1 ]; then
    if [ ! -f "$path" ]; then echo "  ДРЕЙФ (нет файла): $path"; DRIFT=$((DRIFT+1)); return; fi
    if [ "$content" != "$(cat "$path")" ]; then echo "  ДРЕЙФ (отличается): $path"; DRIFT=$((DRIFT+1)); fi
  elif [ "$DRY" = 1 ]; then
    echo "  write $path"
  else
    mkdir -p "$(dirname "$path")"
    printf '%s\n' "$content" > "$path"
  fi
}

ensure_link() {  # ensure_link <цель> <путь>
  local target="$1" path="$2"
  if [ "$CHECK" = 1 ]; then
    if [ ! -L "$path" ] || [ "$(readlink "$path")" != "$target" ]; then
      echo "  ДРЕЙФ (симлинк): $path"; DRIFT=$((DRIFT+1))
    fi
  elif [ "$DRY" = 1 ]; then
    echo "  ln -sfn '$target' '$path'"; DRY_REMOVE_GLOBAL=1
  else
    ln -sfn "$target" "$path"
  fi
}

echo "== Профиль: $PROJECT ($PROFILE) =="
echo "== Глобальные (~/.cline/skills) =="
mkdir -p ~/.cline/skills
for s in "${STALE_GLOBAL[@]}"; do
  if [ "$CHECK" = 0 ] && [ "$DRY" = 0 ]; then rm -rf "$HOME/.cline/skills/$s"; fi
done
for s in "${GLOBAL_SKILLS[@]}"; do
  if [ "$CHECK" = 0 ] && [ "$DRY" = 0 ]; then rm -rf "$HOME/.cline/skills/$s"; fi
  ensure_link "$ROOT/skills/$s" "$HOME/.cline/skills/$s"
done

echo "== Проектные ($AGENT_PREFIX*/.cline) =="
for pair in $AGENTS; do
  dir="${pair%%:*}"; role="${pair##*:}"
  d="$AGENTS_DIR/$dir"
  if [ ! -d "$d" ]; then echo "  SKIP $dir (нет каталога)"; continue; fi
  if [ -n "$ONLY" ] && [ "$dir" != "$ONLY" ]; then continue; fi
  if [ "$CHECK" = 0 ]; then mkdir -p "$d/.cline" "$d/.clinerules"; fi
  if [ "$CHECK" = 0 ] && [ "$DRY" = 0 ]; then rm -rf "$d/.cline/skills"; fi
  if [ "$CHECK" = 0 ]; then mkdir -p "$d/.cline/skills"; fi
  for s in "${GLOBAL_SKILLS[@]}"; do ensure_link "$ROOT/skills/$s" "$d/.cline/skills/$s"; done
  for s in ${ROLE_SKILLS[$role]:-}; do
    ensure_file "$(render "$ROOT/skills/$s/SKILL.md" "$role")" "$d/.cline/skills/$s/SKILL.md"
  done
  for f in "$ROOT"/clinerules/*.md; do
    ensure_file "$(render "$f" "$role")" "$d/.clinerules/$(basename "$f")"
  done
  ensure_file "$(render "$ROOT/roles/$role/00-role.md" "$role")" "$d/.clinerules/00-role.md"
  echo "  OK $dir ($role)"
done

if [ "$CHECK" = 1 ]; then
  if [ "$DRIFT" = 0 ]; then echo "Дрейфа нет."; else echo "Дрейф: $DRIFT файл(ов)/ссылок. Обнови: ./setup.sh --project $PROJECT"; exit 1; fi
fi
echo "Готово."
