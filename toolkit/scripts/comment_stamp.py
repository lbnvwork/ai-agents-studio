#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Штамп комментария: готовая строка для канала статьи — метка времени с часов машины (МСК).

Зачем: агенты ставили метку «по памяти» → в журналах появлялись неактуальные даты.
Скрипт берёт фактическое время (Europe/Moscow, даже если зона машины другая), собирает
строку строго по регламенту «Комментарии задач», проверяет её тем же regex, что и
`check_comments.py`, и по флагу `--write` вставляет запись в свой канал статьи
(новое — сверху) и обновляет `updated` в frontmatter.

Примеры:
  # 1. Напечатать готовую строку (скопировать в канал)
  python3 09-Служебное/Скрипты/comment_stamp.py --agent feb --type отчёт "Разбор БЖ готов"

  # 2. С адресатом ([вопрос]/[ответ] — адресат обязателен; у ответа — время вопроса)
  python3 09-Служебное/Скрипты/comment_stamp.py --agent apr --type вопрос --to Ян "Когда ревью?"
  python3 09-Служебное/Скрипты/comment_stamp.py --agent may --type ответ --to Эйп --ref-time 14:03 "Поправил"

  # 3. Сразу вставить в свой канал статьи (новое сверху) + обновить updated
  python3 09-Служебное/Скрипты/comment_stamp.py --agent jan --type решение \
      --file "03-Задачи/Спринты/Спринт-05/5.32. Инфра линтеры и стиль фронтенда (ESLint, Prettier, Stylelint, Knip).md" \
      --write "Черновик правила отдан Эйпу"

Коды пишущих берутся из профиля проекта (`AGENTS` + владелец); список: `--list-agents`.
"""
import argparse
import datetime
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_comments as cc  # noqa: E402 — формат записи: один источник истины
import project as proj  # noqa: E402 — общий модуль toolkit

P, ARGV = proj.split_argv(sys.argv[1:], os.path.dirname(os.path.abspath(__file__)))
cc.set_profile(P)

BASE = proj.docs_root(__file__)
# Кто пишет: агенты проекта (код → «Имя (роль)») + владелец (AGENT_*/OWNER_* в профиле)
AGENTS = P.comment_authors()
HEADING = cc.CHANNEL


def now_msk():
    """Текущее время по Москве (зона машины может быть любой)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo('Europe/Moscow')), None
    except Exception:
        return datetime.datetime.now(), ('не удалось определить Europe/Moscow — беру время машины; '
                                         'сверь зону: date "+%Y-%m-%d %H:%M %Z"')


def build(who, type_, to, ref_time, text, dt):
    """Строка записи по формату регламента."""
    ts = dt.strftime('%Y-%m-%d %H:%M')
    addr = ''
    if to:
        addr = '→%s%s' % (to, (' ' + ref_time) if ref_time else '')
    line = '- %s МСК · %s · [%s%s] %s' % (ts, who, type_, addr, text.strip())
    return re.sub(r'[ \t]+', ' ', line).strip()


def resolve(path):
    """Путь к статье: абсолютный, от cwd или от корня docs."""
    for cand in (path, os.path.join(os.getcwd(), path), os.path.join(BASE, path)):
        if os.path.exists(cand):
            return cand
    return None


def channel_span(lines, idx):
    """Границы канала: от заголовка до следующего `## ` или конца файла."""
    end = len(lines)
    for i in range(idx + 1, len(lines)):
        if lines[i].startswith('## '):
            end = i
            break
    return idx, end


def norm(s):
    return re.sub(r'\s+', ' ', s).strip().lower()


def role_of(who):
    return who.split('(')[-1].rstrip(')') if '(' in who else ''


def find_channel(lines, who):
    """Индекс заголовка канала автора: точное совпадение, иначе — по имени автора."""
    want, name = norm(who), norm(who.split('(')[0])
    fallback = None
    for i, l in enumerate(lines):
        m = HEADING.match(l)
        if not m:
            continue
        if norm('%s (%s)' % (m.group(1), m.group(2))) == want:
            return i, None
        if norm(m.group(1)) == name and fallback is None:
            fallback = i
    if fallback is not None:
        mm = HEADING.match(lines[fallback])
        return fallback, ('канал найден по имени автора — роль в заголовке «%s (%s)», '
                          'автора записи привёл к нему' % (mm.group(1), mm.group(2)))
    return None, None


def sep_style(lines):
    """Стиль разделителя между каналами в этой статье: '---' или пустая строка."""
    ch = [i for i, l in enumerate(lines) if HEADING.match(l)]
    for i in ch[1:]:
        if lines[i - 1].strip() == '---':
            return '---'
    return ''


def new_channel(lines, who, line):
    """Создаёт канал автора в позиции по конвейеру (РП → руководитель → аналитик → лид → dev → тест → DevOps)."""
    mine = cc.order_key(role_of(who))
    ch = [i for i, l in enumerate(lines) if HEADING.match(l)]
    anchor = None
    for i in ch:
        if cc.order_key(HEADING.match(lines[i]).group(2)) > mine:
            anchor = i
            break
    if anchor is None:
        if ch:
            _, end = channel_span(lines, ch[-1])
            anchor = end
        else:
            anchor = len(lines)
            for i, l in enumerate(lines):
                if l.startswith('## ') and norm(l[3:]).startswith('хронология'):
                    anchor = i
                    break
    while anchor > 0 and not lines[anchor - 1].strip():
        anchor -= 1
    block = ['## Комментарии: %s' % who, '', line]
    if sep_style(lines) == '---' and anchor > 0:
        block = ['---', ''] + block
    ins = [''] + block + ['']
    lines[anchor:anchor] = ins
    # нормализуем только стыки вставки (остальной файл не трогаем)
    lo, hi = max(0, anchor - 2), min(len(lines), anchor + len(ins) + 2)
    i = lo
    while i < hi and i + 1 < len(lines):
        if not lines[i].strip() and not lines[i + 1].strip():
            del lines[i + 1]
            hi -= 1
        else:
            i += 1
    return lines


def insert_entry(text, who, line, dt):
    """Вставка записи в канал <who> (создаёт канал, если его нет) + обновление `updated`."""
    m = re.match(r'^---\n(.*?)\n---', text, re.S)
    if m:
        fm = m.group(1)
        if re.search(r'^updated:', fm, re.M):
            fm2 = re.sub(r'^updated:.*$', 'updated: %s' % dt.strftime('%Y-%m-%d'), fm, flags=re.M)
        else:
            fm2 = fm + '\nupdated: %s' % dt.strftime('%Y-%m-%d')
        text = '---\n' + fm2 + '\n---' + text[m.end():]
    lines = text.split('\n')
    idx, note = find_channel(lines, who)
    if idx is not None and note:
        mm = HEADING.match(lines[idx])
        canon = '%s (%s)' % (mm.group(1), mm.group(2))
        line = line.replace('· %s ·' % who, '· %s ·' % canon, 1)
    created = idx is None
    if created:
        lines = new_channel(lines, who, line)
        idx, _n = find_channel(lines, who)
        if idx is None:
            return None, None, False, 'не удалось создать канал «%s»' % who, line
        return '\n'.join(lines), None, True, note, line
    start, end = channel_span(lines, idx)
    j = start + 1
    while j < end and (not lines[j].strip() or lines[j].strip().startswith('<!--')):
        j += 1
    lines.insert(j, line)
    while start + 1 < len(lines) and not lines[start + 1].strip():
        del lines[start + 1]
    lines.insert(start + 1, '')
    return '\n'.join(lines), None, False, note, line



def main(argv):
    ap = argparse.ArgumentParser(
        description='Строка комментария для канала статьи: метка времени — с часов машины (МСК)')
    ap.add_argument('text', nargs='?', help='текст записи (одна строка)')
    ap.add_argument('--agent', choices=sorted(AGENTS), help='кто пишет (код агента)')
    ap.add_argument('--who', help='кто пишет, как в канале: «Феб (аналитик)»')
    ap.add_argument('--type', dest='type_', choices=sorted(cc.TYPES),
                    help='тип записи: ' + ' · '.join(sorted(cc.TYPES)))
    ap.add_argument('--to', help='адресат (обязателен для [вопрос]/[ответ])')
    ap.add_argument('--ref-time', dest='ref_time', help='ЧЧ:ММ вопроса, на который отвечаем')
    ap.add_argument('--file', help='статья: путь (абсолютный, от cwd или от корня docs)')
    ap.add_argument('--write', action='store_true',
                    help='вставить запись в канал статьи (новое сверху) и обновить updated')
    ap.add_argument('--dry-run', action='store_true', help='с --write: показать результат без записи')
    ap.add_argument('--list-agents', action='store_true', help='показать коды агентов')
    a = ap.parse_args(argv)

    if a.list_agents:
        for k, v in sorted(AGENTS.items()):
            print('%s = %s' % (k, v))
        return 0

    who = a.who or AGENTS.get(a.agent or '')
    if not who:
        ap.error('укажи --agent <код> или --who "<Имя> (<роль>)"')
    if not a.type_:
        ap.error('нужен --type <тип записи>')
    if not a.text:
        ap.error('нужен текст записи (позиционный аргумент)')
    if a.type_ in ('вопрос', 'ответ') and not a.to:
        ap.error('для [%s] адресат обязателен: --to <Имя>' % a.type_)
    if a.type_ == 'ответ' and not a.ref_time:
        print('предупреждение: для [ответ] по регламенту нужна ссылка на минуту вопроса — '
              'укажи --ref-time ЧЧ:ММ', file=sys.stderr)

    dt, warn = now_msk()
    if warn:
        print('предупреждение: ' + warn, file=sys.stderr)
    line = build(who, a.type_, a.to, a.ref_time, a.text, dt)
    if not cc.ENTRY.match(line):
        print('ошибка: строка не проходит проверку формата check_comments:\n  %s' % line, file=sys.stderr)
        return 2

    if not a.write:
        print(line)
        return 0

    if not a.file:
        ap.error('для --write нужен --file <статья>')
    p = resolve(a.file)
    if not p:
        print('ошибка: файл не найден: %s' % a.file, file=sys.stderr)
        return 2
    text = io.open(p, encoding='utf-8').read()
    new, err, created, note, line = insert_entry(text, who, line, dt)
    if err or new is None:
        print('ошибка: %s' % (err or note), file=sys.stderr)
        return 1
    rel = os.path.relpath(p, BASE) if os.path.abspath(p).startswith(os.path.abspath(BASE)) else p
    what = 'канал создан, запись вставлена' if created else 'запись вставлена в канал'
    if a.dry_run:
        print(line)
        print('(dry-run) %s «%s» в %s; updated → %s'
              % (what, who, rel, dt.strftime('%Y-%m-%d')), file=sys.stderr)
        return 0
    io.open(p, 'w', encoding='utf-8').write(new)
    print(line)
    print('%s «%s» (%s); updated → %s. Проверка: '
          'python3 09-Служебное/Скрипты/check_comments.py "%s"' % (what, who, rel, dt.strftime('%Y-%m-%d'), rel),
          file=sys.stderr)
    if note:
        print('примечание: ' + note, file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(ARGV))
