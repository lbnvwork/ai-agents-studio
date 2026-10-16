#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Лента задач: сшивка «вопрос→ответ» и дайджест (5 строк на задачу).

Примеры:
  python3 comments_feed.py --task 5.40                 # лента по задаче
  python3 comments_feed.py --sprint 5 --order desc     # все события спринта
  python3 comments_feed.py --digest --sprint 5         # сводка по задачам
  python3 comments_feed.py --task 5.40 --status-only   # только статусы/вердикты/деплой
"""
import argparse
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import project as proj  # noqa: E402 — общий модуль toolkit

BASE = proj.docs_root(__file__)
TASKS = os.path.join(BASE, '03-Задачи', 'Спринты')
CHANNEL = re.compile(r'^##\s+Комментарии:\s*(.+?)\s*\((.+?)\)\s*$')
SECTION = re.compile(r'^##\s+(.+?)\s*$')
ENTRY = re.compile(
    r'^-\s+(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?)\s+МСК\s+·\s+'
    r'(?P<who>[^·]+?)\s+·\s+\[(?P<type>[а-яё]+)(?:→(?P<addr>[^\]]+))?\]\s*(?P<text>.*)$')
STATUS_TYPES = ('статус', 'вердикт', 'деплой')


def frontmatter(text):
    fm = {}
    m = re.match(r'^---\n(.*?)\n---', text, re.S)
    if m:
        for line in m.group(1).split('\n'):
            mm = re.match(r'^([a-z_]+):\s*(.*)$', line)
            if mm:
                fm[mm.group(1)] = mm.group(2).strip().strip(chr(34)).strip(chr(39)).strip()
    return fm


def parse_entries(path):
    text = io.open(path, encoding='utf-8').read()
    fm = frontmatter(text)
    cur, role = None, ''
    out = []
    for line in text.split('\n'):
        m = CHANNEL.match(line)
        if m:
            cur, role = m.group(1).strip(), m.group(2).strip()
            continue
        if SECTION.match(line):
            cur = None
            continue
        if cur is None:
            continue
        e = ENTRY.match(line.strip())
        if e:
            out.append({
                'file': path, 'task': fm.get('code', '?'), 'sprint': fm.get('sprint', '?'),
                'status': fm.get('status', '?'), 'awaiting': fm.get('awaiting', '—'),
                'ts': e.group('ts'), 'who': e.group('who').strip(),
                'who_bare': e.group('who').strip().split('(')[0].strip(), 'role': role,
                'type': e.group('type'), 'addr': (e.group('addr') or '').strip(),
                'text': e.group('text').strip(), 'children': [],
            })
    return out, fm


def collect(args):
    rows = []
    for base, dirs, files in os.walk(TASKS):
        for name in sorted(files):
            if not name.endswith('.md'):
                continue
            path = os.path.join(base, name)
            entries, fm = parse_entries(path)
            if not entries:
                continue
            if args.task and fm.get('code') != args.task:
                continue
            if args.sprint and str(fm.get('sprint', '')).strip() != str(args.sprint):
                continue
            if args.since and entries and entries[0]['ts'] < args.since:
                pass
            rows.extend(entries)
    if args.since:
        rows = [e for e in rows if e['ts'][:10] >= args.since]
    if args.author:
        rows = [e for e in rows if args.author.lower() in e['who'].lower()]
    if args.type:
        wanted = {t.strip() for t in args.type.split(',')}
        rows = [e for e in rows if e['type'] in wanted]
    if args.status_only:
        rows = [e for e in rows if e['type'] in STATUS_TYPES]
    return rows


def stitch(rows):
    by_key = {}
    for e in rows:
        by_key.setdefault((e['file'], e['who_bare'], e['ts'][11:16]), []).append(e)
    for e in rows:
        if e['type'] == 'ответ' and e['addr']:
            parts = e['addr'].split()
            if len(parts) >= 2 and ':' in parts[-1]:
                target = by_key.get((e['file'], parts[0], parts[-1][:5]), [])
                for t in target:
                    if t is not e and not t['children'].count(e):
                        t['children'].append(e)
                        break
    return [e for e in rows if not any(e in t['children'] for t in rows)]


def print_feed(rows, order):
    tops = stitch(rows)
    tops.sort(key=lambda e: e['ts'], reverse=(order == 'desc'))
    for e in tops:
        print('%s · %s · %s · [%s]%s %s' % (e['ts'], e['task'], e['who'], e['type'],
                                            (' → ' + e['addr']) if e['addr'] else '', e['text'][:220]))
        for c in sorted(e['children'], key=lambda x: x['ts']):
            print('     └ %s · %s · [%s] %s' % (c['ts'][11:16], c['who'], c['type'], c['text'][:200]))


def digest(rows):
    tasks = {}
    for e in rows:
        tasks.setdefault(e['task'], []).append(e)
    for code in sorted(tasks):
        entries = sorted(tasks[code], key=lambda x: x['ts'])
        e0 = entries[-1]
        reports = [x for x in entries if x['type'] in ('отчёт', 'деплой')]
        last_report = reports[-1]['text'][:150] if reports else '—'
        checks = [x for x in entries if re.search(r'тест|phpunit|vitest|провер|прогон', x['text'], re.I)]
        last_check = checks[-1]['text'][:150] if checks else '—'
        answered = {x['addr'].split()[0] for x in entries if x['type'] == 'ответ' and x['addr']}
        open_q = [x for x in entries if x['type'] in ('вопрос', 'замечание') and x['who_bare'] not in answered]
        blocker = open_q[-1]['text'][:150] if open_q else 'нет'
        print('%s | статус: %s | ждёт: %s' % (code, e0['status'], e0['awaiting']))
        print('   сделано: %s' % last_report)
        print('   проверено: %s' % last_check)
        print('   блокеры/вопросы: %s' % blocker)
        print('   последнее событие: %s · %s · [%s]' % (e0['ts'], e0['who'], e0['type']))
        print('')


def main():
    p = argparse.ArgumentParser()
    proj.add_args(p)
    p.add_argument('--task')
    p.add_argument('--sprint')
    p.add_argument('--since')
    p.add_argument('--author')
    p.add_argument('--type')
    p.add_argument('--order', choices=['asc', 'desc'], default='asc')
    p.add_argument('--status-only', action='store_true')
    p.add_argument('--digest', action='store_true')
    args = p.parse_args()
    rows = collect(args)
    if not rows:
        print('событий не найдено')
        return
    if args.digest:
        digest(rows)
    else:
        print_feed(rows, args.order)
    print('событий: %d' % len(rows))


if __name__ == '__main__':
    main()
