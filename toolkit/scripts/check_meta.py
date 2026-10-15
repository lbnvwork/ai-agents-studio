#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка frontmatter статей задач (задача 5.40).

Запуск: python3 09-Служебное/Скрипты/check_meta.py
Проверяет: обязательные поля, значения из словаря, отсутствие '#' в значениях,
наличие `awaiting` у активных задач и его значение по словарю профиля (AWAITING).
Профиль ищется как у остальных скриптов toolkit (см. toolkit/project.py): --project/--layer/--core,
иначе AGENTS_* или файл .agents рядом со скриптом. Код возврата 1 — есть нарушения.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project as proj  # noqa: E402 — общий модуль toolkit

DOCS = proj.docs_root(__file__)
ROOT = os.path.join(DOCS, '03-Задачи')
SKIP_DIRS = ('_Шаблоны', 'Планы спринтов', 'Архив')

VOCAB = {
    'type': {'feature', 'fix', 'refactor', 'doc', 'infra', 'test', 'planning', 'analysis'},
    'status': {'spec', 'planned', 'in_progress', 'review', 'testing', 'deploy', 'done', 'blocked', 'cancelled'},
    'priority': {'P0', 'P1', 'P2', 'P3'},
    'size': {'S', 'M', 'L'},
}
REQUIRED = ('code', 'title', 'type', 'status', 'sprint')
# Для задач «в работе» обязательны ещё приоритет, размер и держатель мяча.
REQUIRED_WHEN_WORKING = ('priority', 'size', 'awaiting')
WORKING = {'planned', 'in_progress', 'review', 'testing', 'deploy', 'blocked'}
# Для задач плана (спринт ≥ 5) обязательны поля планирования.
REQUIRED_WHEN_PLANNED = ('est', 'order', 'goal')


def frontmatter(path):
    text = io.open(path, encoding='utf-8').read()
    m = re.match(r'^---\n(.*?)\n---', text, re.S)
    if not m:
        return None
    out = {}
    for line in m.group(1).split('\n'):
        mm = re.match(r'^([a-z_]+):\s*(.*)$', line)
        if mm:
            out[mm.group(1)] = mm.group(2).strip().strip(chr(34)).strip(chr(39)).strip()
    return out


def main(argv):
    P, _rest = proj.split_argv(argv, os.path.dirname(os.path.abspath(__file__)))

    problems = []
    checked = 0
    for base, dirs, files in os.walk(ROOT):
        if any(s in base for s in SKIP_DIRS):
            continue
        for name in sorted(files):
            if not name.endswith('.md'):
                continue
            path = os.path.join(base, name)
            fm = frontmatter(path)
            if not fm or 'code' not in fm:
                continue
            checked += 1
            rel = os.path.relpath(path, os.path.join(ROOT, '..'))
            for key in REQUIRED:
                if not fm.get(key):
                    problems.append('%s: нет поля %s' % (rel, key))
            for key, allowed in VOCAB.items():
                val = fm.get(key, '').strip()
                if val and val not in allowed:
                    problems.append('%s: %s=%r — вне словаря' % (rel, key, val))
            for key, val in fm.items():
                if '#' in val:
                    problems.append('%s: поле %s содержит комментарий шаблона: %r' % (rel, key, val[:60]))
            awaiting = fm.get('awaiting', '').strip()
            if awaiting and P.awaiting and awaiting not in P.awaiting:
                problems.append('%s: awaiting=%r — вне словаря профиля (ключ AWAITING)' % (rel, awaiting))
            if fm.get('status', '').strip() in WORKING:
                for key in REQUIRED_WHEN_WORKING:
                    if not fm.get(key):
                        problems.append('%s: задача в работе без поля %s' % (rel, key))
            try:
                sprint = int(fm.get('sprint', '0') or 0)
            except ValueError:
                sprint = 0
            if sprint >= 5 and fm.get('status', '').strip() != 'cancelled':
                for key in REQUIRED_WHEN_PLANNED:
                    if not fm.get(key):
                        problems.append('%s: задача плана (спринт %d) без поля %s' % (
                            rel, sprint, key))
    print('проверено статей: %d' % checked)
    if problems:
        print('нарушений: %d' % len(problems))
        for p in problems:
            print(' - ' + p)
        return 1
    print('нарушений нет')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
