#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка инвариантов в правилах ядра (clinerules/*.md).

Зачем: правила рендерятся во все воркспейсы; при сжатии/рефакторинге нельзя потерять
запреты и гейты. Скрипт падает, если хоть один инвариант исчез из правил.

Запуск: python3 toolkit/scripts/check_rules.py [--budget N]
  --budget N  — дополнительно проверить, что суммарный размер правил <= N байт
"""
import glob
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def rules_dir():
    """Каталог правил ядра.

    Из ядра: <core>/toolkit/scripts/check_rules.py → <core>/clinerules.
    Из копии в docs проекта (09-Служебное/Скрипты) ядро ищем через AGENTS_CORE/.agents;
    не нашли — возвращаем None (проверка не применима, копия не должна ломать CI проекта).
    """
    local = os.path.normpath(os.path.join(HERE, '..', '..', 'clinerules'))
    if os.path.isdir(local):
        return local
    core = os.environ.get('AGENTS_CORE')
    if not core:
        d = HERE
        for _ in range(4):
            cfg = os.path.join(d, '.agents')
            if os.path.isfile(cfg):
                for line in io.open(cfg, encoding='utf-8'):
                    if line.strip().startswith('CORE='):
                        core = line.split('=', 1)[1].strip()
                break
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    if core and os.path.isdir(os.path.join(core, 'clinerules')):
        return os.path.join(core, 'clinerules')
    return None


RULES_DIR = rules_dir()
RULES = sorted(glob.glob(os.path.join(RULES_DIR, '*.md'))) if RULES_DIR else []

# (id, описание, regex) — каждый инвариант обязан найтись хотя бы в одном файле
INVARIANTS = [
    ('commit-ban', 'запрет коммитов агентам', r'не выполняет[^\n]*git commit'),
    ('commit-owner', 'коммит делает руководитель', r'руководител'),
    ('force-push', 'запрет force-push', r'--force'),
    ('wip', 'WIP 1–2 задачи на агента', r'WIP'),
    ('kanban-truth', 'Канбан — источник истины', r'Канбан[^\n]*источник истины'),
    ('pm-only-moves', 'карточки двигает только РП', r'только РП'),
    ('four-fields', 'смена статуса 4 полями', r'4 поля|четыре поля'),
    ('awaiting', 'поле awaiting обязательно', r'awaiting'),
    ('gates-bz', 'гейт: сверка БЖ Аналитиком', r'БЖ[- ]сверка'),
    ('gates-clinical', 'гейт: клиническая сверка', r'Клиническая сверка'),
    ('gates-security', 'гейт: security-ревью', r'Безопасность'),
    ('gates-threat', 'релиз без модели угроз не закрывается', r'модел[ьи] угроз'),
    ('make-ci', 'единая команда make ci', r'make ci'),
    ('report-block', 'блок КОММИТЫ в отчёте', r'КОММИТЫ'),
    ('report-names', 'в блоке только названия', r'только названия'),
    ('studio-section', 'раздел проекта принадлежит студийному агенту', r'только в свой раздел'),
    ('commit-exception', 'исключение по коммиту — только свой раздел под хуком', r'pre-commit'),
    ('section-by-name', 'ссылки по названию раздела, не по номеру', r'по названию'),
    ('commit-commands', 'названия коммитов — готовыми git-командами', r'git add[^\n]*&&[^\n]*git commit'),
    ('actual-date', 'фактическая дата записи', r'фактическ'),
    ('docker-down', 'остановка стека после задачи', r'docker compose down|down`'),
    ('transfer-new-code', 'перенос = новый код', r'новый код'),
    ('escalation', 'эскалация', r'Эскалация'),
    ('docs-separate', 'доки в отдельном репо', r'DOCS_REPO'),
    ('pull-first', 'pull перед правкой доков', r'git pull'),
    ('dead-code', 'мёртвый код не оправдан тестами', r'мёртв'),
]


def main():
    budget = None
    if '--budget' in sys.argv:
        budget = int(sys.argv[sys.argv.index('--budget') + 1])

    if not RULES:
        print('правила ядра не найдены (запуск из копии?) — проверка пропущена')
        return 0

    text = {}
    total = 0
    for path in RULES:
        body = open(path, encoding='utf-8').read()
        text[os.path.basename(path)] = body
        total += len(body.encode('utf-8'))
    joined = '\n'.join(text.values())

    missing = []
    for key, title, pattern in INVARIANTS:
        if not re.search(pattern, joined, re.IGNORECASE):
            missing.append((key, title))

    print('правил: %d файлов, %d байт' % (len(RULES), total))
    print('инвариантов проверено: %d' % len(INVARIANTS))
    if missing:
        print('ПОТЕРЯНЫ ИНВАРИАНТЫ (%d):' % len(missing))
        for key, title in missing:
            print('  - %-18s %s' % (key, title))
    if budget is not None:
        status = 'ok' if total <= budget else 'ПРЕВЫШЕН'
        print('бюджет: %d байт, факт %d — %s' % (budget, total, status))
        if total > budget:
            return 1
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
