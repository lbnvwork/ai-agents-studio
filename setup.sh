#!/usr/bin/env bash
# Развёртывание настроек агентов (правила + скиллы) из ядра ai-agents-studio.
#
# Ядро нейтрально: в правилах/ролях/скиллах стоят плейсхолдеры {{KEY}}, значения
# берутся из профиля проекта profiles/<project>/project.env (в git не хранится).
# Само ядро имён проектов не знает.
#
# Модель данных: агент (каталог, код, стек) принадлежит дорожке (lane) — пулу
# компетенции с ёмкостью; наборы скиллов задаются по дорожке (дефолты — в ядре),
# переопределяются по агенту. Карточку и скилл можно переопределить из профиля.
#
# Запуск из корня ядра:
#   ./setup.sh                                     # единственный профиль — автоопределение
#   ./setup.sh --project <project>                 # выбрать проект явно
#   ./setup.sh --layer /path/to/<project>-agents   # проектный слой: профиль + переопределения
#   ./setup.sh --project <project> --only <каталог агента>   # точечно (пилот)
#   ./setup.sh --project <project> --root /path/to/projects  # другой корень клонов
#   ./setup.sh --project <project> --dry-run       # показать, что будет сделано
#   ./setup.sh --project <project> --check         # проверить дрейф копий (ничего не пишет)
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
PROJECT=""
LAYER=""
DRY=0
CHECK=0
ONLY=""
ROOT_OVERRIDE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT="${2:-}"; shift ;;
    --layer)   LAYER="${2:-}"; shift ;;
    --root)    ROOT_OVERRIDE="${2:-}"; shift ;;
    --only)    ONLY="${2:-}"; shift ;;
    --dry-run) DRY=1 ;;
    --check)   CHECK=1; DRY=1 ;;
    -h|--help) awk 'NR==1{next} /^set -euo/{exit} {print}' "$0"; exit 0 ;;
  esac
  shift
done

# Источник данных: проектный слой (--layer) или локальный profiles/<project>/ в ядре.
if [ -n "$LAYER" ]; then
  if [ ! -d "$LAYER" ]; then echo "нет каталога проектного слоя: $LAYER"; exit 2; fi
  PROFILE_DIR="$(cd "$LAYER" && pwd)"
  [ -n "$PROJECT" ] && echo "== --layer задан: имя проекта берётся из слоя (--project не нужен) =="
else
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
         echo "укажи явно: ./setup.sh --project <имя> (или --layer <путь к слою>)"
         exit 2 ;;
    esac
  fi
  PROFILE_DIR="$ROOT/profiles/$PROJECT"
fi

PROFILE="$PROFILE_DIR/project.env"
if [ ! -f "$PROFILE" ]; then
  echo "нет профиля: $PROFILE"
  echo "создай: cp profiles/_template/project.env.dist <каталог>/project.env"
  exit 2
fi
# Значения профиля читаем как ДАННЫЕ: содержимое не выполняется (бэктики, $(), ! — текст,
# а не команды). Учитываем кавычки и хвостовые комментарии — как project.py у скриптов.
load_profile() {
  local line key val quote rest
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    case "$line" in *=*) ;; *) continue ;; esac
    key="${line%%=*}"; val="${line#*=}"
    key="${key//[[:space:]]/}"
    case "$key" in ''|*[!A-Za-z0-9_]*) continue ;; esac
    case "$val" in
      \"*|\'*)
        quote="${val:0:1}"; rest="${val:1}"; val="${rest%%"$quote"*}" ;;
      *) val="${val%%#*}" ;;
    esac
    val="${val#"${val%%[![:space:]]*}"}"
    val="${val%"${val##*[![:space:]]}"}"
    export "$key=$val"
  done < "$PROFILE"
}
load_profile
if [ -z "${PROJECT:-}" ]; then echo "в профиле не задан PROJECT: $PROFILE"; exit 2; fi
if [ -n "$ROOT_OVERRIDE" ]; then AGENTS_ROOT="$ROOT_OVERRIDE"; fi
AGENTS_DIR="$AGENTS_ROOT"
if [ -z "${AGENTS_ROOT:-}" ]; then echo "в профиле не задан AGENTS_ROOT: $PROFILE"; exit 2; fi

# --- методология (живёт в ядре) ---------------------------------------------
# Какие скиллы получает дорожка по умолчанию. Профиль может перекрыть
# (LANE_SKILLS_<ДОРОЖКА>) или уточнить по агенту (AGENT_SKILLS_<КОД>).
declare -A CORE_LANE_SKILLS=(
  [pm]="review-code status-briefing find-dead-code"
  [analytics]=""
  [lead]="run-tests explain-db write-aquarium write-adr review-code find-dead-code"
  [dev]="run-tests explain-db write-aquarium find-dead-code"
  [test]="run-tests make-postman write-e2e-scenario"
  [devops]="run-tests release find-dead-code"
)
GLOBAL_SKILLS=(git-workflow sync-env write-instruction)
STALE_GLOBAL=(explain-db make-postman run-tests write-adr write-e2e-scenario)
DRIFT=0

# --- данные профиля ---------------------------------------------------------
# LANES="дорожка:ёмкость:название …"
declare -A LANE_CAP=() LANE_RU=()
if [ -n "${LANES:-}" ]; then
  for l in $LANES; do
    lane="${l%%:*}"; rest="${l#*:}"
    LANE_CAP[$lane]="${rest%%:*}"; LANE_RU[$lane]="${rest#*:}"
  done
fi

key() { echo "$1" | tr '[:lower:]-' '[:upper:]_'; }

# Набор скиллов: переопределение по агенту → по дорожке (профиль) → дефолт дорожки (ядро)
agent_skills() {
  local code="$1" lane="$2" var val
  var="AGENT_SKILLS_$(key "$code")"; val="${!var:-}"
  if [ -n "$val" ]; then echo "$val"; return; fi
  var="LANE_SKILLS_$(key "$lane")"; val="${!var:-}"
  if [ -n "$val" ]; then echo "$val"; return; fi
  echo "${CORE_LANE_SKILLS[$lane]:-}"
}

# Стем стека (docker-проект DOCKER_PREFIX_<стем>, порты PORT_<СТЕМ>_*):
# по умолчанию код агента, переопределяется в профиле (AGENT_STEM_<КОД>).
agent_stem() {
  local code="$1" var
  var="AGENT_STEM_$(key "$code")"
  echo "${!var:-$code}"
}

# Контент скилла: проектный слой / профиль (по агенту → по дорожке → по проекту) → ядро
pick_skill() {
  local name="$1" code="$2" lane="$3" p
  for p in "$PROFILE_DIR/skills/$name.$code.md" \
           "$PROFILE_DIR/skills/$name.$lane.md" \
           "$PROFILE_DIR/skills/$name.md" \
           "$ROOT/skills/$name/SKILL.md"; do
    if [ -f "$p" ]; then echo "$p"; return 0; fi
  done
  return 1
}

# Карточка агента: проектный слой / профиль → ядро
pick_role() {
  local code="$1" p="$PROFILE_DIR/roles/$code.md"
  if [ -f "$p" ]; then echo "$p"; else echo "$ROOT/roles/$code/00-role.md"; fi
}

# Рендер: значения профиля + ролевые/агентские подстановки
render() {
  local src="$1" dir="$2" code="$3" lane="$4" out stem ru app_ptr db_ptr web_ptr
  local pairs pair k v t_var s_var d_var skills_list
  out="$(cat "$src")"
  stem="$(agent_stem "$code")"
  ru="$(key "$stem")"
  app_ptr="PORT_${ru}_APP"; db_ptr="PORT_${ru}_DB"; web_ptr="PORT_${ru}_WEB"
  t_var="AGENT_TITLE_$(key "$code")"; s_var="AGENT_SHORT_$(key "$code")"; d_var="AGENT_DOES_$(key "$code")"
  skills_list=""
  for s in $(printf '%s\n' "${GLOBAL_SKILLS[@]}" $(agent_skills "$code" "$lane") | sort -u); do
    skills_list="${skills_list}\`$s\`, "
  done
  skills_list="${skills_list%, }"
  pairs=(
    "{{AGENT_DIR}}=$AGENTS_DIR/$dir"
    "{{AGENT_CODE}}=$code"
    "{{AGENT_TITLE}}=${!t_var-}"
    "{{AGENT_SHORT}}=${!s_var-}"
    "{{AGENT_DOES}}=${!d_var-}"
    "{{SKILLS_LIST}}=$skills_list"
    "{{LANE}}=$lane" "{{LANE_RU}}=${LANE_RU[$lane]:-}" "{{LANE_CAP}}=${LANE_CAP[$lane]:-}"
    "{{DOCKER_PROJECT}}=${DOCKER_PREFIX:-}_${stem}"
    "{{PORT_APP}}=${!app_ptr:-}" "{{PORT_DB}}=${!db_ptr:-}" "{{PORT_WEB}}=${!web_ptr:-}"
    "{{PROJECT}}=$PROJECT" "{{PROJECT_TITLE}}=${PROJECT_TITLE:-}"
    "{{AGENTS_ROOT}}=$AGENTS_ROOT" "{{AGENT_PREFIX}}=${AGENT_PREFIX:-}"
    "{{CODE_REPO}}=${CODE_REPO:-}" "{{CODE_REPO_URL}}=${CODE_REPO_URL:-}" "{{CODE_BRANCH}}=${CODE_BRANCH:-}"
    "{{DOCS_REPO}}=${DOCS_REPO:-}" "{{DOCS_REPO_URL}}=${DOCS_REPO_URL:-}" "{{DOCS_BRANCH}}=${DOCS_BRANCH:-}"
    "{{PM_DIR}}=${PM_DIR:-}" "{{DOCKER_PREFIX}}=${DOCKER_PREFIX:-}" "{{DOCKER_PM}}=${DOCKER_PM:-}"
    "{{DOCKER_DEV}}=${DOCKER_DEV:-}" "{{DOCKER_PROD}}=${DOCKER_PROD:-}" "{{PROD_DATA_DIR}}=${PROD_DATA_DIR:-}"
    "{{PORT_DEV_APP}}=${PORT_DEV_APP:-}" "{{PORT_DEV_DB}}=${PORT_DEV_DB:-}" "{{PORT_DEV_WEB}}=${PORT_DEV_WEB:-}"
    "{{PORT_PROD_APP}}=${PORT_PROD_APP:-}" "{{PORT_PROD_DB}}=${PORT_PROD_DB:-}"
    "{{CUR_SPRINT}}=${CUR_SPRINT:-}" "{{SPRINT_FROM}}=${SPRINT_FROM:-}" "{{SPRINT_TO}}=${SPRINT_TO:-}"
    "{{DEADLINE_D1}}=${DEADLINE_D1:-}" "{{DEADLINE_D2}}=${DEADLINE_D2:-}"
    "{{SPRINT_DAYS}}=${SPRINT_DAYS:-}" "{{CAP_DEV}}=${CAP_DEV:-}" "{{CAP_LEAD}}=${CAP_LEAD:-}"
    "{{CAP_ANALYTICS}}=${CAP_ANALYTICS:-}" "{{CAP_TEST}}=${CAP_TEST:-}" "{{CAP_DEVOPS}}=${CAP_DEVOPS:-}" "{{CAP_PM}}=${CAP_PM:-}"
  )
  for pair in "${pairs[@]}"; do
    k="${pair%%=*}"; v="${pair#*=}"
    out="${out//"$k"/$v}"
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
    echo "  ln -sfn '$target' '$path'"
  else
    ln -sfn "$target" "$path"
  fi
}

ensure_lines() {  # ensure_lines <файл> <строка> … — добавляет отсутствующие строки
  local file="$1"; shift
  local line added=0 norm
  for line in "$@"; do
    norm="$(printf '%s' "$line" | tr -d '[:space:]')"
    if [ -f "$file" ] && tr -d '[:space:]' < "$file" | grep -qF "$norm"; then continue; fi
    if [ "$CHECK" = 1 ]; then echo "  ДРЕЙФ (нет строки '$line'): $file"; DRIFT=$((DRIFT+1)); continue; fi
    if [ "$DRY" = 1 ]; then echo "  append '$line' → $file"; added=1; continue; fi
    mkdir -p "$(dirname "$file")"
    printf '%s\n' "$line" >> "$file"
    added=1
  done
  [ "$added" = 1 ] || true
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

echo "== Агенты (по профилю: каталог:код:дорожка) =="
for pair in $AGENTS; do
  dir="${pair%%:*}"; rest="${pair#*:}"; code="${rest%%:*}"; lane="${rest#*:}"
  d="$AGENTS_DIR/$dir"
  if [ ! -d "$d" ]; then echo "  SKIP $dir (нет каталога)"; continue; fi
  if [ -n "$ONLY" ] && [ "$dir" != "$ONLY" ]; then continue; fi
  if [ -f "$(pick_role "$code")" ]; then :; else echo "  SKIP $dir (нет карточки агента: $code)"; continue; fi
  if [ -z "${LANE_RU[$lane]:-}${LANE_CAP[$lane]:-}" ]; then echo "  ВНИМАНИЕ: дорожка '$lane' не описана в LANES ($dir)"; fi
  if [ "$CHECK" = 0 ]; then mkdir -p "$d/.cline" "$d/.clinerules"; fi
  if [ "$CHECK" = 0 ] && [ "$DRY" = 0 ]; then rm -rf "$d/.cline/skills"; fi
  if [ "$CHECK" = 0 ]; then mkdir -p "$d/.cline/skills"; fi
  for s in "${GLOBAL_SKILLS[@]}"; do ensure_link "$ROOT/skills/$s" "$d/.cline/skills/$s"; done
  for s in $(agent_skills "$code" "$lane"); do
    src="$(pick_skill "$s" "$code" "$lane")" || { echo "  ПРОПУСК скилла $s (нет файла)"; continue; }
    ensure_file "$(render "$src" "$dir" "$code" "$lane")" "$d/.cline/skills/$s/SKILL.md"
  done
  for f in "$ROOT"/clinerules/*.md; do
    ensure_file "$(render "$f" "$dir" "$code" "$lane")" "$d/.clinerules/$(basename "$f")"
  done
  ensure_file "$(render "$(pick_role "$code")" "$dir" "$code" "$lane")" "$d/.clinerules/00-role.md"
  echo "  OK $dir ($code · дорожка $lane)"
done

# --- toolkit: PM-скрипты в docs каждого клона --------------------------------
# Скрипты живут в ядре (toolkit/), в проект уезжают копиями (как правила), рядом —
# конфиг `.agents` с путём к ядру и именем профиля (локальный, в git не нужен).
echo "== Toolkit (скрипты PM в docs проекта) =="
for pair in $AGENTS; do
  dir="${pair%%:*}"; rest="${pair#*:}"; code="${rest%%:*}"; lane="${rest#*:}"
  d="$AGENTS_DIR/$dir"
  [ -n "$ONLY" ] && [ "$dir" != "$ONLY" ] && continue
  if [ ! -d "$d/docs/09-Служебное" ]; then echo "  SKIP $dir (нет docs)"; continue; fi
  scripts_dir="$d/docs/09-Служебное/Скрипты"
  if [ "$CHECK" = 0 ]; then mkdir -p "$scripts_dir"; fi
  for f in "$ROOT/toolkit/project.py" "$ROOT"/toolkit/scripts/*.py; do
    ensure_file "$(cat "$f")" "$scripts_dir/$(basename "$f")"
  done
  ensure_file "CORE=$ROOT
PROJECT=$PROJECT" "$scripts_dir/.agents"
  ensure_lines "$d/docs/.gitignore" ".agents" "__pycache__/"
  echo "  OK $dir (toolkit: $(ls "$ROOT"/toolkit/scripts/*.py | wc -l) скриптов + project.py)"
done

if [ "$CHECK" = 1 ]; then
  if [ "$DRIFT" = 0 ]; then echo "Дрейфа нет."; else echo "Дрейф: $DRIFT файл(ов)/ссылок. Обнови: ./setup.sh --project $PROJECT"; exit 1; fi
fi
echo "Готово."
