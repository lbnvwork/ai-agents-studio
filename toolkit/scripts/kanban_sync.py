#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Синхронизация канбана с данными статей (задача 5.40).

Пересобирает карточки из статусов статей текущего спринта: спринт 4 и старше
уходят с доски (они в архиве). Уже написанные вручную «хвосты» карточек (PR, версия)
сохраняются — по коду в ссылке.

Запуск: python3 09-Служебное/Скрипты/kanban_sync.py [--write]
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import project as proj  # noqa: E402 — общий модуль toolkit

DOCS = proj.docs_root(__file__)
TASKS = os.path.join(DOCS, '03-Задачи/Спринты')
KANBAN = os.path.join(DOCS, '03-Задачи/Канбан.md')

P, ARGV = proj.split_argv(sys.argv[1:], os.path.dirname(os.path.abspath(__file__)))
CUR = P.cur_sprint

COLUMN = {'spec': 'Надо делать', 'planned': 'Анализ', 'in_progress': 'Делаю', 'review': 'Ревью',
          'testing': 'Тестирую', 'deploy': 'Деплой', 'done': 'Готово',
          'blocked': 'Отложено', 'cancelled': 'Отменено'}
STEP = {'spec': 'в очереди', 'planned': 'в анализе', 'in_progress': 'в работе', 'review': 'на ревью',
        'testing': 'на тестах', 'deploy': 'выкатка', 'done': 'готово', 'blocked': 'ждёт решения',
        'cancelled': 'отменена'}
# Хвост карточки сохраняем, если это факт. Перегенерируем только «служебные» хвосты
# вида «· Имя — в очереди» (их пишет сам скрипт): иначе карточка врёт о состоянии.
STATUS_TAIL = re.compile(
    r'^·\s*[^—·]+—\s*(в очереди|к запуску|в анализе|в работе|на ревью|на тестах|выкатка|готово|'
    r'ждёт решения|отменена)\s*$')
# Короткие имена агентов — из профиля (AGENT_SHORT_<КОД>)
ORDER = ['Надо делать', 'Анализ', 'Делаю', 'Ревью', 'Тестирую', 'Деплой', 'Готово',
         'Отложено', 'Отменено']


def read(p):
    return io.open(p, encoding='utf-8').read()


def frontmatter(path):
    text = read(path)
    m = re.match(r'^---\n(.*?)\n---', text, re.S)
    fm = {}
    for line in (m.group(1).split('\n') if m else []):
        mm = re.match(r'^([a-z_]+):\s*(.*)$', line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"')
    return fm


def rows():
    out = []
    for base, dirs, files in os.walk(TASKS):
        if 'Архив' in base:
            continue
        for name in sorted(files):
            if not name.endswith('.md'):
                continue
            fm = frontmatter(os.path.join(base, name))
            if fm.get('code') and int(fm.get('sprint') or 0) == CUR:
                fm['_file'] = name[:-3]
                out.append(fm)
    out.sort(key=lambda r: (float(r.get('order') or 99), r.get('code')))
    return out


def short_title(title, limit=40):
    t = re.split(r'\s*[—(]\s*', title)[0].strip().rstrip(',:;')
    return t if len(t) <= limit else t[:limit - 1].rstrip() + '…'


def existing_tails():
    """Код → сохранённый вручную хвост карточки («· исполнитель — факт…»)."""
    if not os.path.exists(KANBAN):
        return {}
    tails = {}
    for line in read(KANBAN).split('\n'):
        m = re.match(r'^-\s*\[[ x]\]\s*\[\[([^|\]]+)\|([^\]]+)\]\]\s*(.*)$', line)
        if m:
            code = m.group(2).strip().split()[0]
            tails.setdefault(code, m.group(3))
    return tails


def card(r, tail):
    who = P.short(r.get('assignee', '')) if r.get('assignee') else '—'
    short = short_title(' '.join(r.get('title', '').split()))
    generated = '· %s — %s' % (who, STEP.get(r.get('status'), ''))
    if tail and not STATUS_TAIL.match(tail.strip()):
        body = tail
    else:
        body = generated
    box = 'x' if r.get('status') in ('done', 'cancelled') else ' '
    return '- [%s] [[%s|%s %s]] %s' % (box, r['_file'], r.get('code'), short, body.strip())


def main():
    apply = '--write' in ARGV
    text = read(KANBAN)
    head = text.split('\n## ', 1)[0]
    settings = ''
    m = re.search(r'%%\s*kanban:settings.*?%%', text, re.S)
    if m:
        settings = m.group(0)
    tails = existing_tails()
    data = rows()
    by_col = {}
    for r in data:
        by_col.setdefault(COLUMN.get(r.get('status'), 'Надо делать'), []).append(r)
    out = [head.rstrip('\n'), '']
    for col in ORDER:
        out.append('## ' + col)
        out.append('')
        for r in by_col.get(col, []):
            out.append(card(r, tails.get(r.get('code'))))
        out.append('')
        out.append('')
    if settings:
        out += [settings, '']
    new = '\n'.join(out).rstrip('\n') + '\n'
    print('карточек: %d (спринт %d)' % (sum(len(v) for v in by_col.values()), CUR))
    for col in ORDER:
        print('  %-12s %d' % (col, len(by_col.get(col, []))))
    if new == text:
        print('без изменений')
        return
    if apply:
        io.open(KANBAN, 'w', encoding='utf-8').write(new)
        print('Канбан обновлён')
    else:
        print('(DRY-RUN — не записано)')


if __name__ == '__main__':
    main()
