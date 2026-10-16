#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разбор таблиц плана спринтов в данные (задача 5.40: «план = данные»).

Служебный скрипт разового импорта: читает markdown-таблицы плана
(состав: код | задача | цель→KPI | тип | FUNC | оценка | приоритет | зависит от)
и отдаёт JSON для plan_apply.py. Регламент — 09-Служебное/Регламенты/План и данные.md.

Служебный разовый скрипт: запускается, когда план ведут таблицами и нужно
перенести состав в данные статей (дальше источник истины — статьи).

Вход:  docs/03-Задачи/Планы спринтов/Детальный план спринтов.md (--plan PATH)
Выход: JSON на stdout или в файл (--write PATH) — вход для plan_apply.py.
Профиль: --core/--project/--layer, иначе AGENTS_* или .agents (см. project.py).

Структура: {sprint: {"meta": {...}, "rows": [ {code, title, goal, type, func, est,
priority, depends_on, carried_from, order} ]}}
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import project as proj  # noqa: E402 — общий модуль toolkit

P, ARGV = proj.split_argv(sys.argv[1:], os.path.dirname(os.path.abspath(__file__)))

DOCS = P.docs
PLAN = os.path.join(DOCS, '03-Задачи/Планы спринтов/Детальный план спринтов.md')

TYPE_MAP = {'ref': 'refactor', 'refactor': 'refactor', 'feature': 'feature', 'fix': 'fix',
            'doc': 'doc', 'infra': 'infra', 'test': 'test', 'planning': 'planning',
            'analysis': 'analysis'}


def parse_sprint_number(text):
    m = re.search(r'Спринт\s+(\d+)', text)
    return int(m.group(1)) if m else None


def split_meta(text):
    """Ёмкость, KPI, цель из прозы секции."""
    meta = {}
    m = re.search(r'\*\*Ёмкость:\*\*\s*([^\.\n]+)', text)
    if m:
        meta['capacity'] = m.group(1).strip().rstrip('.').strip()
    m = re.search(r'\*\*Цель:\*\*\s*(.+?)(?=\n>|\n\n)', text, re.S)
    if m:
        meta['goal'] = ' '.join(m.group(1).split())
    m = re.search(r'\*\*KPI[^:]*:\*\*\s*(.+?)(?=\n\n|\n>|\n##)', text, re.S)
    if m:
        meta['kpi'] = ' '.join(m.group(1).split())
    return meta


def parse_dates(title):
    m = re.search(r'\((\d{2}\.\d{2})\s*[–-]\s*(\d{2}\.\d{2})', title)
    if m:
        return m.group(1), m.group(2)
    return None, None


def main():
    plan = PLAN
    if '--plan' in ARGV:
        plan = ARGV[ARGV.index('--plan') + 1]
    text = io.open(plan, encoding='utf-8').read()
    lines = text.split('\n')

    sprints = {}
    cur = None
    # Заголовки секций: ## Спринт 5 — ... / ### Спринт 8 — ...
    for i, line in enumerate(lines):
        m = re.match(r'^#{2,3}\s+(Спринт\s+\d+.*)$', line)
        if m:
            num = parse_sprint_number(m.group(1))
            if num is None:
                continue
            title = m.group(1).strip()
            # тело секции до следующего заголовка ##/### того же/меньшего уровня
            body = []
            for j in range(i + 1, len(lines)):
                if re.match(r'^#{2,3}\s', lines[j]):
                    break
                body.append(lines[j])
            body_text = '\n'.join(body)
            start, end = parse_dates(title)
            meta = split_meta(body_text)
            meta.update({'title': title, 'start': start, 'end': end})
            sprints.setdefault(num, {'meta': {}, 'rows': []})
            sprints[num]['meta'] = meta
            cur = num
            order = 0
            for row in body:
                if not row.startswith('|'):
                    continue
                cells = [c.strip() for c in row.strip().strip('|').split('|')]
                if len(cells) < 8 or set(cells[0]) <= set('- '):
                    continue
                code_cell = cells[0]
                cm = re.search(r'(\d+)\.(\d+)', code_cell)
                if not cm:
                    continue
                code = '%s.%s' % (cm.group(1), cm.group(2))
                if int(cm.group(1)) != num:
                    continue
                order += 1
                carried = None
                if '⤴' in code_cell:
                    carried = 'перенос'
                title_task = cells[1].strip()
                goal = cells[2].strip()
                ttype = cells[3].strip()
                func = cells[4].strip()
                est = cells[5].strip()
                prio = cells[6].strip()
                deps = cells[7].strip()
                # «перенос из спринта N» — уточняем источник
                m2 = re.search(r'перенос[а-я]* из спринта\s+(\d+)', title_task, re.I)
                if carried and m2:
                    carried = m2.group(1)
                rows = sprints.setdefault(num, {'meta': {}, 'rows': []})
                rows['rows'].append({
                    'code': code,
                    'title': title_task,
                    'goal': goal,
                    'type': TYPE_MAP.get(ttype, ttype),
                    'func': [f.strip() for f in func.split('/') if f.strip() and f.strip() != '—'],
                    'est': None if est in ('—', '-', '') else float(est.replace(',', '.')),
                    'priority': prio if prio != '—' else 'P3',
                    'depends_on': [] if deps in ('—', '-', '') else [d.strip() for d in deps.split(',')],
                    'carried_from': carried,
                    'order': order,
                })

    out = {}
    for num, data in sorted(sprints.items()):
        if not data['rows']:
            continue
        out[str(num)] = data
    result = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=False)
    if '--write' in ARGV:
        path = ARGV[ARGV.index('--write') + 1]
        io.open(path, 'w', encoding='utf-8').write(result + '\n')
        print('записано: %s (спринтов: %d, строк: %d)' % (
            path, len(out), sum(len(v['rows']) for v in out.values())))
    else:
        print(result)


if __name__ == '__main__':
    main()
