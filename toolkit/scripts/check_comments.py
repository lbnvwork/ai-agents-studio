#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка статьи задачи по модели 5.40: «Контекст передачи» + каналы + бюджеты.

Запуск: python3 09-Служебное/Скрипты/check_comments.py <файл статьи> [...]
Статьи старого образца (без секций `## Комментарии: Имя (роль)`) пропускаются.
Код возврата 1 — есть нарушения.
"""
import datetime
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import project as proj  # noqa: E402 — общий модуль toolkit

CHANNEL = re.compile(r'^##\s+Комментарии:\s*(.+?)\s*\((.+?)\)\s*$')
SECTION = re.compile(r'^##\s+(.+?)\s*$')
ENTRY = re.compile(
    r'^-\s+(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?)\s+МСК\s+·\s+'
    r'(?P<who>[^·]+?)\s+·\s+\[(?P<type>[а-яё]+)(?:→(?P<addr>[^\]]+))?\]\s*(?P<text>.*)$')
TYPES = {'статус', 'отчёт', 'вопрос', 'ответ', 'вердикт', 'замечание', 'деплой', 'решение'}
FORBIDDEN = ('СДЕЛАНО:', 'ФАЙЛЫ:', 'БЛОКЕРЫ:', 'ЗАМЕТКИ:')
BUDGET = {'S': 10, 'M': 20, 'L': 40}
# Порядок каналов = конвейер. Ключевые слова и позиции строятся из профиля:
# первая дорожка (РП) → владелец (руководитель) → остальные дорожки в порядке AGENTS.
# Сортируем ключи по длине (убывание), чтобы «devops» срабатывал раньше «dev».
_KEYS = None


def role_keys(P):
    keys = []
    first_lane = P.agents[0]['lane'] if P.agents else 'pm'
    for a in P.agents:
        if a['lane'] == first_lane:
            for kw in (a['role'], a['lane'], a['code'], a['short']):
                if kw:
                    keys.append((kw.lower(), 0))
    for name, meta in P.awaiting.items():
        if meta.get('type') == 'owner':
            keys.append((name.lower(), 1))
    keys.append(('руководител', 1))
    lanes_order = []
    for a in P.agents:
        if a['lane'] != first_lane and a['lane'] not in lanes_order:
            lanes_order.append(a['lane'])
    for i, ln in enumerate(lanes_order, start=2):
        ru = (P.lanes.get(ln, {}) or {}).get('ru', '')
        if ru:
            keys.append((ru.lower(), i))
        for a in P.agents:
            if a['lane'] != ln:
                continue
            for kw in (a['role'], a['lane'], a['code'], a['short']):
                if kw:
                    keys.append((kw.lower(), i))
    return sorted(keys, key=lambda kv: -len(kv[0]))


def set_profile(P):
    """Запоминает ключи каналов для текущего профиля (нужно и comment_stamp)."""
    global _KEYS
    _KEYS = role_keys(P)
    return _KEYS


def sections(text):
    out, order, cur = {}, [], None
    for line in text.split('\n'):
        m = SECTION.match(line)
        if m:
            cur = m.group(1)
            order.append(cur)
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return out, order


def frontmatter(text):
    fm = {}
    m = re.match(r'^---\n(.*?)\n---', text, re.S)
    if m:
        for line in m.group(1).split('\n'):
            mm = re.match(r'^([a-z_]+):\s*(.*)$', line)
            if mm:
                fm[mm.group(1)] = mm.group(2).strip().strip(chr(34)).strip(chr(39)).strip()
    return fm


def order_key(role, keys=None):
    r = (role or '').lower()
    ks = _KEYS if keys is None else keys
    for kw, key in (ks or []):
        if kw in r:
            return key
    return len(ks or []) + 1


def main(argv):
    P, argv = proj.split_argv(argv, os.path.dirname(os.path.abspath(__file__)))
    set_profile(P)
    if not argv:
        print('использование: check_comments.py <файл статьи> [...]')
        return 2
    problems, checked = [], 0
    for path in argv:
        text = io.open(path, encoding='utf-8').read()
        sec, order = sections(text)
        channels = [s for s in order if CHANNEL.match('## ' + s)]
        rel = os.path.basename(path)
        if not channels:
            print('%s: статья старого образца — пропущена' % rel[:60])
            continue
        checked += 1
        fm = frontmatter(text)
        size = (fm.get('size') or 'M').strip()
        budget = BUDGET.get(size, 20)

        if 'Контекст передачи' not in order:
            problems.append('%s: нет секции «Контекст передачи»' % rel)
        else:
            body = [x for x in sec['Контекст передачи'] if x.strip()]
            if len(body) > 25:
                problems.append('%s: «Контекст передачи» %d строк (бюджет 25)' % (rel, len(body)))

        keys = [order_key(CHANNEL.match('## ' + c).group(2)) for c in channels]
        if keys != sorted(keys):
            problems.append('%s: каналы не в порядке конвейера: %s' % (rel, '; '.join(channels)))

        total = 0
        for ch in channels:
            name = CHANNEL.match('## ' + ch).group(1).strip()
            body = [x for x in sec[ch] if x.strip() and not x.strip().startswith('<!--')]
            total += len(body)
            for line in body:
                if line.strip().startswith('###'):
                    continue
                e = ENTRY.match(line.strip())
                if not e:
                    problems.append('%s / %s: запись не по формату: %r' % (rel, name, line.strip()[:70]))
                    continue
                who = e.group('who').strip()
                if who.split('(')[0].strip() != name.split('(')[0].strip():
                    problems.append('%s / %s: автор %r не совпадает с каналом' % (rel, name, who))
                t = e.group('type')
                if t not in TYPES:
                    problems.append('%s / %s: неизвестный тип [%s]' % (rel, name, t))
                # Метка времени — по фактическим часам машины: дата из будущего = нарушение
                ts = e.group('ts')
                fmt = '%Y-%m-%d %H:%M:%S' if len(ts) > 16 else '%Y-%m-%d %H:%M'
                try:
                    dt = datetime.datetime.strptime(ts, fmt)
                except ValueError:
                    dt = None
                now = datetime.datetime.now()
                if dt is not None and dt > now + datetime.timedelta(minutes=2):
                    problems.append(
                        '%s / %s: метка времени в будущем — %s (сейчас на машине %s); '
                        'сверь часы командой \'date "+%%Y-%%m-%%d %%H:%%M %%Z"\'' % (
                            rel, name, ts, now.strftime('%Y-%m-%d %H:%M')))
                if t in ('вопрос', 'ответ') and not e.group('addr'):
                    problems.append('%s / %s: [%s] без адресата' % (rel, name, t))
                for bad in FORBIDDEN:
                    if bad in line:
                        problems.append('%s / %s: в журнале отчётный блок %s' % (rel, name, bad))
        if total > budget:
            problems.append('%s: журнал %d строк (бюджет для size=%s — %d)' % (rel, total, size, budget))

        for s in order:
            low = s.lower()
            if 'аквариум' in low:
                rows = [x for x in sec[s] if x.strip().startswith('|')]
                if len(rows) > 17:
                    problems.append('%s: «Аквариум» %d строк таблицы (бюджет 15 + заголовки)' % (rel, len(rows)))
                if (fm.get('type') or '').strip() in ('doc', 'infra', 'test'):
                    problems.append('%s: для type=%s секция «Аквариум» не предусмотрена' % (rel, fm.get('type')))
            if low.startswith('реализация'):
                body = [x for x in sec[s] if x.strip() and not x.strip().startswith('<!--')]
                if len(body) > 10:
                    problems.append('%s: «Реализация» %d строк (бюджет 10)' % (rel, len(body)))

    print('проверено статей нового образца: %d' % checked)
    if problems:
        print('нарушений: %d' % len(problems))
        for p in problems:
            print(' - ' + p)
        return 1
    print('нарушений нет')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
