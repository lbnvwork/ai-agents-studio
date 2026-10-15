#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор плана спринтов из данных (задача 5.40: «план = данные»).

Источники: frontmatter статей `03-Задачи/Спринты/**` + шапки `Планы спринтов/Спринт-NN.md`.
Режимы:
  (без флагов)  напечатать план в stdout
  --write       перегенерировать «Детальный план спринтов.md» + AUTO-области шапок спринтов
  --check       проверить полноту данных (код ↔ статья, обязательные поля) — анти-потеря
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project as proj  # noqa: E402 — общий модуль toolkit

P, ARGV = proj.split_argv(sys.argv[1:], os.path.dirname(os.path.abspath(__file__)))

DOCS = proj.docs_root(__file__)
TASKS = os.path.join(DOCS, '03-Задачи/Спринты')
PLANS = os.path.join(DOCS, '03-Задачи/Планы спринтов')
PLAN_DOC = os.path.join(PLANS, 'Детальный план спринтов.md')

# Дорожки, ёмкости, подписи — из профиля проекта (toolkit/project.py).
# Порядок витрин = порядок дорожек в LANES профиля.
LANE_ORDER = P.lane_order
LANE_CAP = P.lane_caps()
LANE_RU = {k: v['ru'] for k, v in P.lanes.items()}
LANE_OF = {}
for _lane in list(LANE_ORDER) + [a['lane'] for a in P.agents]:
    for _a in P.agents:
        if _a['lane'] == _lane:
            LANE_OF.setdefault(_a['dir'], P.lane_of(_a['dir']))
ST_EMOJI = {'spec': '⬜ spec', 'planned': '🔵 planned', 'in_progress': '🚧 in_progress',
            'review': '👀 review', 'testing': '🧪 testing', 'deploy': '🚀 deploy',
            'done': '✅ done', 'blocked': '⛔ blocked', 'cancelled': '✖ cancelled'}
FIELDS = ('code', 'title', 'type', 'status', 'sprint', 'priority', 'size', 'est',
          'order', 'goal', 'assignee', 'awaiting', 'func', 'depends_on', 'updated')

CUR = P.cur_sprint           # текущий спринт (ключ CUR_SPRINT в профиле)
HOURS = P.hours_per_day      # часов в чел-дне
FUNC_PAGE = os.path.join(PLANS, 'Покрытие ТЗ (FUNC).md')
DASHBOARD = os.path.join(DOCS, '09-Служебное/Дашборд руководителя.md')
ARCH_PERIOD = P.archive_periods


def hrs(v):
    return g(fnum(v) * HOURS)


def fmt_date4(d):
    """2026-09-20 → 20.09.2026"""
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', str(d or ''))
    return '%s.%s.%s' % (m.group(3), m.group(2), m.group(1)) if m else ''


def deadline_lines():
    """Блок «Дедлайны»: даты и пояснения — ключи DEADLINE_D1/D2 и *_NOTE в профиле."""
    out = []
    for tag, date, note in (('Д1', P.deadline_d1, P.deadline_d1_note),
                            ('Д2', P.deadline_d2, P.deadline_d2_note)):
        if date:
            out.append('- **%s · %s** — %s' % (tag, fmt_date4(date), note or '—'))
    return '\n'.join(out) or '— дедлайны не заданы —'


def fmt_date(d):
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', str(d or ''))
    return '%s.%s.%s' % (m.group(3), m.group(2), m.group(1)[2:]) if m else ''


def term_of(head, n=None):
    """Срок спринта: точные даты, иначе период, иначе архив."""
    a, b = fmt_date(head.get('start')), fmt_date(head.get('end'))
    if a and b:
        return '%s — %s' % (a, b)
    return head.get('period') or ARCH_PERIOD.get(str(n), '—')


def dash_sprints(rows, heads):
    out = ['| Спринт | Срок | Этап | Задач | План, чел-дни | План, часы | Ёмкость dev | Загрузка dev | Прогресс |',
           '|---|---|---|---|---|---|---|---|---|']
    for n in range(P.sprint_from, P.sprint_to + 1):
        r = tasks_of(rows, n)
        head = heads.get(n, {})
        s = stat(r)
        act = stat([x for x in r if x.get('status') not in ('done', 'cancelled')])
        cap = fnum(head.get('capacity'))
        term = term_of(head, n)
        out.append('| **%d** | %s | %s | %d | %s | %s | %s | %s | %s |' % (
            n, term or '—', head.get('stage', '—'), s['n'], g(s['est']), hrs(s['est']),
            head.get('capacity_note', '—') if cap else '—',
            verdict(act, cap) if cap else '✅ закрыт', prog(r)))
    return '\n'.join(out)


def dash_team(rows, heads):
    r = tasks_of(rows, CUR)
    head = heads.get(CUR, {})
    out = ['| Агент | Дорожка | Задач в работе | Осталось, чел-дни | Осталось, часы | Ёмкость | Загрузка | Вердикт |',
           '|---|---|---|---|---|---|---|---|']
    for who, (ln, title) in LANE_OF.items():
        mine = [x for x in r if x.get('assignee') == who and x.get('status') not in ('done', 'cancelled')]
        if not mine:
            continue
        est = sum(fnum(x.get('est')) for x in mine)
        cap = LANE_CAP[ln]
        pct = round(100 * est / cap) if cap else 0
        flag = '⚠️ перегруз' if pct > 110 else ('🟡 плотно' if pct > 95 else '🟢 запас')
        out.append('| %s | %s | %d | %s | %s | %d | %d%% | %s |' % (
            title, LANE_RU[ln], len(mine), g(est), hrs(est), cap, pct, flag))
    s = stat(r)
    closed = sum(fnum(x.get('est')) for x in r if x.get('status') in ('done', 'cancelled'))
    left = s['est'] - closed
    out += ['', '> Ёмкость dev-дорожки на спринт — **%d × %d чел-дней** (%s). План спринта: '
                '**%s чел-дней / %s ч**, из них закрыто **%s**, осталось **%s чел-дней / %s ч**. '
                'Ёмкость всех дорожек — **%d чел-дней**. Загрузка и вердикт считаются по **незакрытым** задачам.' % (
                    len(P.agents_in_lane('dev')), P.lanes.get('dev', {}).get('cap') or 0,
                    head.get('capacity_note', ''), g(s['est']), hrs(s['est']), g(closed),
                    g(left), hrs(left), P.total_capacity())]
    return '\n'.join(out)



def dash_scope(rows, heads):
    r = tasks_of(rows, CUR)
    cap = fnum(heads.get(CUR, {}).get('capacity')) or P.lane_cap_total('dev')
    devs = P.agents_in_lane('dev')
    dev = [x for x in r if x.get('assignee') in devs and x.get('status') not in ('done', 'cancelled')]
    left = sum(fnum(x.get('est')) for x in dev)
    queue = sorted(dev, key=lambda x: fnum(x.get('order')))
    keep, move, acc = [], [], 0.0
    for x in queue:
        e = fnum(x.get('est'))
        if acc + e <= cap:
            keep.append(x)
            acc += e
        else:
            move.append(x)
    out = ['**Dev-дорожка спринта %d:** не закрыто **%s чел-дней (%s ч)** при ёмкости **%s** → %s.' % (
        CUR, g(left), hrs(left), g(cap),
        '⚠️ перегруз на %s чел-дней' % g(left - cap) if left > cap
        else '✅ влезает, запас %s чел-дней' % g(cap - left))]
    hdr = ['| Код | Задача | Приор. | Оценка, чел-дни | Часы | Порядок |',
           '|---|---|---|---|---|---|']

    def rows_md(items):
        return ['| [[%s\\|%s]] | %s | %s | %s | %s | %s |' % (
            x['_file'], x['code'], x.get('title', '')[:56], x.get('priority', '—'),
            g(x.get('est')), hrs(x.get('est')), x.get('order', '')) for x in items]

    if move:
        out += ['', '**Влезает в ёмкость: %d задач / %s чел-дней (%s ч)**' % (
            len(keep), g(acc), hrs(acc)), ''] + hdr + rows_md(keep)
        me = sum(fnum(x.get('est')) for x in move)
        out += ['', '**На перенос в следующий спринт: %d задач / %s чел-дней (%s ч)** — кандидаты '
                    '(сначала низкий приоритет и конец очереди):' % (len(move), g(me), hrs(me)), ''] \
               + hdr + rows_md(move)
        out += ['', '> Перенос оформляется **новым кодом** следующего спринта + `carried_from`; '
                    'после переноса — `python3 09-Служебное/Скрипты/sprint_plan.py --write`.',
                '> Очередь запуска — поле **`order`** (порядок в этом списке); `priority` — флаг важности, '
                    'а не сортировка. Меняете порядок — правьте `order` в статьях, затем `--write`.']
        p0 = [x['code'] for x in move if x.get('priority') == 'P0']
        if p0:
            out += ['', '> ⚠️ В хвосте оказались **P0**: %s — либо снять блокировку, либо разбить задачу, '
                        'либо переставить `order`.' % ', '.join(p0)]
    return '\n'.join(out)


def dash_archive(rows, heads):
    out = ['| Спринт | Период | Задач | Закрыто (done) | Отменено | Реестр |',
           '|---|---|---|---|---|---|']
    for n in (1, 2, 3, 4):
        r = tasks_of(rows, n)
        if not r:
            continue
        s = stat(r)
        head = heads.get(n, {})
        period = head.get('period') or head.get('start', '') or ARCH_PERIOD.get(str(n), '—')
        out.append('| Спринт %d | %s | %d | **%d** | %d | [[Спринт %d]] |' % (
            n, period, s['n'], s['status'].get('done', 0), s['status'].get('cancelled', 0), n))
    out += ['', '> Спринт закрыт, когда в нём не осталось статусов `spec`, `planned`, `in_progress`, '
                '`review`, `testing`, `deploy`: незакрытые уходят в следующий спринт новым кодом '
                '(поле `carried_from`). Здесь — итоги: сколько задач закрыто и отменено.']
    return '\n'.join(out)


def func_map(rows, min_sprint=4):
    m = {}
    for r in rows:
        if r.get('_sprint', 0) < min_sprint:
            continue
        for f in (r.get('func') or '').strip('[]').replace('"', '').split(','):
            f = f.strip().replace('FUNC-', '')
            if f:
                m.setdefault('FUNC-%s' % f, []).append(r)
    return m


def dash_func(rows):
    m = func_map(rows)
    cov = {}
    for f, items in m.items():
        key = func_coverage(f)
        cov[key] = cov.get(key, 0) + 1
    legend = ('✅ реализовано · 🟡 частично · ⬜ в плане · ➖ не в Альфе (Бета/Промпилот/Поддержка) · '
              '⛔ отложено/отменено')
    out = ['| Покрытие | Функций | Что значит |', '|---|---|---|']
    for key in ['✅', '🟡', '⬜', '➖', '⛔']:
        if cov.get(key):
            out.append('| %s | %d | %s |' % (key, cov[key], COVERAGE_RU.get(key, '')))
    out += ['', '> Значки: ' + legend, '',
            '> Показаны задачи **от спринта 4** (архив 1–3 — в «Пройденных спринтах»).', '',
            '| FUNC | Функция | Модуль | Покрытие | Спринты плана | Задачи плана | Пункты ТЗ |',
            '|---|---|---|---|---|---|---|']
    for line in func_lines():
        f = line['func']
        items = sorted(m.get(f, []), key=lambda r: (r['_sprint'], fnum(r.get('order'))))
        codes = ', '.join('[[%s\\|%s]]' % (r['_file'], r['code']) for r in items) or '—'
        out.append('| %s | %s | %s | %s | %s | %s | %s |' % (
            f, line['title'], line['module'], line['coverage'], line['sprints'], codes, line['tz']))
    out += ['', '> Источник матрицы — [[FUNC-матрица]] (ТЗ §6.1); статусы покрытия ведёт Аналитик, '
                'задачи и спринты подтягиваются из статей автоматически.']
    return '\n'.join(out)



COVERAGE_RU = {'✅': 'реализовано', '🟡': 'частично', '⬜': 'в плане (Альфа/Бета)',
               '➖': 'не в Альфе (Бета/Промпилот/Поддержка)', '⛔': 'отложено/отменено'}


def func_lines():
    """Строки реестра FUNC из файла «Покрытие ТЗ (FUNC)»."""
    if not os.path.exists(FUNC_PAGE):
        return []
    out = []
    for line in io.open(FUNC_PAGE, encoding='utf-8').read().split('\n'):
        if '[func::' not in line:
            continue
        item = {}
        for key, val in re.findall(r'\[([a-z_]+)::\s*([^\]]*)\]', line):
            item[key] = val.strip()
        if item.get('func'):
            out.append(item)
    return out


def func_coverage(f):
    for item in func_lines():
        if item['func'] == f:
            return item.get('coverage', '—')
    return '—'


def sync_func_page(rows):
    """Проставить в файле FUNC поле [tasks:: коды] из статей."""
    if not os.path.exists(FUNC_PAGE):
        return 0
    m = func_map(rows)
    text = io.open(FUNC_PAGE, encoding='utf-8').read()
    updated = 0
    out = []
    for line in text.split('\n'):
        mm = re.search(r'\[func::\s*(FUNC-\d+)\]', line)
        if not mm:
            out.append(line)
            continue
        items = sorted(m.get(mm.group(1), []), key=lambda r: (r['_sprint'], fnum(r.get('order'))))
        codes = ', '.join(r['code'] for r in items) or '—'
        new = '[tasks:: %s]' % codes
        line2 = (re.sub(r'\[tasks::[^\]]*\]', new, line) if re.search(r'\[tasks::[^\]]*\]', line)
                 else line.rstrip() + ' ' + new)
        out.append(line2)
        if line2 != line:
            updated += 1
    if updated:
        io.open(FUNC_PAGE, 'w', encoding='utf-8').write('\n'.join(out))
    return updated


def frontmatter(path):
    text = io.open(path, encoding='utf-8').read()
    m = re.match(r'^---\n(.*?)\n---', text, re.S)
    if not m:
        return None, text
    fm = {}
    for line in m.group(1).split('\n'):
        mm = re.match(r'^([a-z_]+):\s*(.*)$', line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"')
    return fm, text


def load_articles():
    rows = []
    for base, dirs, files in os.walk(TASKS):
        if 'Архив' in base:
            continue
        for name in sorted(files):
            if not name.endswith('.md'):
                continue
            path = os.path.join(base, name)
            fm, _ = frontmatter(path)
            if not fm or not fm.get('code'):
                continue
            try:
                sprint = int(str(fm.get('sprint', '')).strip() or 0)
            except ValueError:
                sprint = 0
            fm['_file'] = name[:-3]
            fm['_sprint'] = sprint
            rows.append(fm)
    return rows


def load_headers():
    heads = {}
    if not os.path.isdir(PLANS):
        return heads
    names = [(name, os.path.join(PLANS, name)) for name in sorted(os.listdir(PLANS))]
    arch = os.path.join(PLANS, 'Пройденные спринты')
    if os.path.isdir(arch):
        names += [(name, os.path.join(arch, name)) for name in sorted(os.listdir(arch))]
    for name, path in names:
        m = re.match(r'^Спринт[- ](\d+)(\.md)?\.md$', name) or re.match(r'^Спринт-(\d+)\.md$', name)
        if not m:
            continue
        n = int(m.group(1))
        fm, text = frontmatter(path)
        if fm is None:
            fm = {}
        if not fm.get('sprint'):
            fm['sprint'] = n
        m2 = re.search(r'^##\s+Примечания и риски\s*\n(.*?)(?=\n##\s|\Z)', text, re.S | re.M)
        fm['_notes'] = m2.group(1).strip() if m2 else ''
        fm.setdefault('stage', '')
        heads[n] = fm
    return heads


def fnum(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return 0.0


def g(v):
    f = fnum(v)
    return ('%g' % f) if f else '—'


def lane_of(assignee):
    return P.lane_of(assignee)[0]


def tasks_of(rows, sprint):
    out = [r for r in rows if r['_sprint'] == sprint]
    out.sort(key=lambda r: (fnum(r.get('order')) or 99, str(r.get('code'))))
    return out


def stat(rows):
    """Сводка по набору задач."""
    s = {'n': len(rows), 'est': 0.0, 'lanes': {}, 'status': {}}
    for r in rows:
        e = fnum(r.get('est'))
        s['est'] += e
        ln = lane_of(r.get('assignee', ''))
        s['lanes'][ln] = s['lanes'].get(ln, 0.0) + e
        st = r.get('status', '?')
        s['status'][st] = s['status'].get(st, 0) + 1
    return s


def load_of(rows, who):
    return sum(fnum(r.get('est')) for r in rows if r.get('assignee') == who)


def refresh_region(path, name, content):
    text = io.open(path, encoding='utf-8').read()
    start = '<!-- AUTO:%s -->' % name
    end = '<!-- /AUTO:%s -->' % name
    if start not in text or end not in text:
        return False
    head = text.split(start)[0]
    tail = text.split(end, 1)[1]
    # Пустые строки вокруг содержимого обязательны: без них Obsidian склеивает
    # первую строку таблицы с HTML-комментарием и таблица не рендерится.
    new = head + start + '\n\n' + content.strip('\n') + '\n\n' + end + tail
    if new == text:
        return False
    io.open(path, 'w', encoding='utf-8').write(new)
    return True


def write_all(rows, heads):
    doc = plan_doc(rows, heads)
    io.open(PLAN_DOC, 'w', encoding='utf-8').write(doc)
    print('записан: %s (%d строк)' % (os.path.basename(PLAN_DOC), doc.count('\n')))
    for n, head in sorted(heads.items()):
        if n <= 3:
            continue
        r = tasks_of(rows, n)
        path = os.path.join(PLANS, 'Спринт-%02d.md' % n)
        if not os.path.exists(path):
            continue
        ok_t = refresh_region(path, 'TABLE', table(r))
        txt = summary_lines(r, head) if r else '- задач в плане не найдено (проверить frontmatter)'
        ok_s = refresh_region(path, 'SUMMARY', txt)
        print('  шапка %d: таблица %s, сводка %s' % (n, 'ok' if ok_t else '—',
                                                    'ok' if ok_s else '—'))
    if os.path.exists(DASHBOARD):
        for name, content in (('SPRINTS', dash_sprints(rows, heads)),
                              ('TEAM', dash_team(rows, heads)),
                              ('SCOPE', dash_scope(rows, heads)),
                              ('ARCHIVE', dash_archive(rows, heads)),
                              ('FUNC', dash_func(rows))):
            ok = refresh_region(DASHBOARD, name, content)
            print('  дашборд %s: %s' % (name, 'ok' if ok else '—'))
    print('  покрытие ТЗ: полей tasks обновлено — %d' % sync_func_page(rows))


def check(rows, heads):
    problems = []
    codes = {}
    for r in rows:
        c = str(r.get('code'))
        codes.setdefault(c, []).append(r)
    for c, group in sorted(codes.items()):
        if len(group) > 1:
            problems.append('дубль кода %s: %s' % (c, ', '.join(x['_file'] for x in group)))
    for r in rows:
        c = str(r.get('code'))
        n = r['_sprint']
        if c.count('.') == 1:
            pref = int(c.split('.')[0])
            if n >= P.sprint_from and pref != n:
                problems.append('%s: код не совпадает со спринтом (sprint=%s, file=%s)' % (
                    c, n, r['_file']))
        if n >= P.sprint_from and r.get('status') not in ('cancelled',):
            for f in ('est', 'order', 'goal'):
                if not r.get(f):
                    problems.append('%s: нет поля %s (file=%s)' % (c, f, r['_file']))
    plan_codes = set()
    for n in range(P.min_plan_sprint, P.sprint_to + 1):
        plan_codes |= set(str(r.get('code')) for r in tasks_of(rows, n))
    for n, head in sorted(heads.items()):
        if n >= P.min_plan_sprint and not head.get('capacity'):
            problems.append('шапка спринта %d: нет поля capacity' % n)
    print('проверено статей: %d · спринтов: %d' % (len(rows), len(set(r['_sprint'] for r in rows))))
    tot = stat(rows)
    print('план (спринты %d–%d): %s чел-дней на %d задач' % (
        P.min_plan_sprint, P.sprint_to,
        g(stat([r for r in rows if r['_sprint'] >= P.min_plan_sprint])['est']), tot['n']))
    if problems:
        print('нарушений: %d' % len(problems))
        for p in problems:
            print(' - ' + p)
        return 1
    print('нарушений нет')
    return 0


def main():
    rows = load_articles()
    heads = load_headers()
    if '--write' in ARGV:
        write_all(rows, heads)
        return 0
    if '--check' in ARGV:
        return check(rows, heads)
    print(plan_doc(rows, heads))
    return 0




def prog(rows):
    s = stat(rows)
    order = ['in_progress', 'review', 'testing', 'deploy', 'blocked', 'planned', 'spec', 'done', 'cancelled']
    items = ['%s %d' % (ST_EMOJI.get(k, k), s['status'][k])
             for k in order if s['status'].get(k)]
    return ' · '.join(items) or '—'


def summary_table(rows, heads, numbers):
    out = ['| Спринт | Срок | Этап | Задач | План, чел-дни | Ёмкость dev | Вердикт | Прогресс |',
           '|---|---|---|---|---|---|---|---|']
    for n in numbers:
        r = tasks_of(rows, n)
        head = heads.get(n, {})
        s = stat(r)
        if n <= 3:
            out.append('| %d | архив | — | %d | — | — | — | %s |' % (n, s['n'], prog(r)))
            continue
        term = head.get('capacity_note') or g(head.get('capacity'))
        period = term_of(head, n)
        cap = fnum(head.get('capacity'))
        if not cap:
            term = 'архив'
        out.append('| **%d** | %s | %s | %d | %s | %s | %s | %s |' % (
            n, period, head.get('stage', ''), s['n'], g(s['est']), term,
            verdict(s, cap) if cap else '✅ закрыт', prog(r)))
    return '\n'.join(out)


def agents_table(rows, numbers):
    out = ['| Агент | Дорожка | Задач | План, чел-дни | Ёмкость/спринт | Спринты |',
           '|---|---|---|---|---|---|']
    for who, (ln, title) in LANE_OF.items():
        mine = [r for r in rows if r.get('assignee') == who and r['_sprint'] in numbers]
        if not mine:
            continue
        sp = sorted(set(r['_sprint'] for r in mine))
        load = sum(fnum(r.get('est')) for r in mine)
        out.append('| %s | %s | %d | %s | %s | %s |' % (
            title, LANE_RU[ln], len(mine), g(load), LANE_CAP[ln],
            ', '.join(str(x) for x in sp)))
    return '\n'.join(out)


def carries_table(rows):
    dep = sorted([r for r in rows if r.get('carried_from')],
                 key=lambda r: (r['_sprint'], fnum(r.get('order'))))
    if not dep:
        return '— переносов нет —'
    out = ['| Стало | Было | Задача | Спринт |', '|---|---|---|---|']
    for r in dep:
        out.append('| [[%s\\|%s]] | %s | %s | %d |' % (
            r['_file'], r['code'], r['carried_from'], r.get('title', '')[:70], r['_sprint']))
    return '\n'.join(out)


def load_legend():
    return '\n'.join([
        '- **Тип:** `feature` · `fix` · `refactor` · `doc` · `infra` · `test` · `planning` · `analysis`',
        '- **Приоритет:** P0 (дедлайн/блокер) · P1 · P2 · P3',
        '- **Оценка (est):** чел-дни разработки (1 дев); дорожки лида, теста, DevOps, аналитика — отдельно',
        '- **Статус:** ⬜ spec (в очереди) · 🔵 planned · 🚧 in_progress · 👀 review · 🧪 testing · '
        '🚀 deploy · ✅ done · ⛔ blocked · ✖ cancelled',
        '- **Older/новые поля статей:** `est` (оценка), `order` (очередь запуска в спринте), '
        '`goal` (цель → KPI), `carried_from` (перенос «было → стало»)',
    ])


def plan_doc(rows, heads):
    # Спринты: архив + всё, что есть в шапках или в статьях (до SPRINT_TO)
    numbers = [n for n in range(1, P.sprint_to + 1)
               if n < P.sprint_from or heads.get(n) or tasks_of(rows, n)]
    out = [
        '# Детальный план спринтов',
        '',
        '> ⚠️ **Файл генерируется — правки здесь не сохранятся.** Обновить: '
        '`python3 09-Служебное/Скрипты/sprint_plan.py --write`.',
        '> Источники: frontmatter статей `03-Задачи/Спринты/**` + шапки `Планы спринтов/Спринт-NN.md`.',
        '> Витрины: [[Дашборд руководителя]] (планировщик) · [[Команда и ёмкость]] (ёмкость дорожек) · '
        '[[Общий план спринтов]] (roadmap, FUNC, дедлайны).',
        '',
        '## Легенда',
        load_legend(),
        '',
        '## Дедлайны',
        deadline_lines(),
        '',
        '## Сводка по спринтам',
        summary_table(rows, heads, numbers),
        '',
        '## Загрузка по агентам (спринты %d–%d)' % (P.sprint_from, P.sprint_to),
        agents_table(rows, set(range(P.sprint_from, P.sprint_to + 1))),
        '',
        '> Ёмкость лида/теста/аналитика/DevOps/РП в плане представлена только «своими» задачами '
        '(постановки, e2e, миграции, регламенты); их доля внутри задач девов в `est` не выделяется — '
        'поэтому низкая загрузка этих дорожек означает запас, а не простой.',
        '',
        '## Переносы «было → стало»',
        carries_table(rows),
        '',
    ]
    for n in range(P.sprint_from, P.sprint_to + 1):
        r = tasks_of(rows, n)
        if not r:
            continue
        head = heads.get(n, {})
        s = stat(r)
        term = term_of(head, n)
        out += [
            '## Спринт %d — %s' % (n, head.get('short') or head.get('_short', '') or head.get('period', '')),
            '',
            '> **Статус:** %s · **Срок:** %s · **Этап:** %s' % (
                {'current': '🔄 идёт', 'planned': '⬜ запланирован',
                 'done': '✅ пройден'}.get(head.get('status', ''), head.get('status', '—')),
                term, head.get('stage', '—')),
            '> **Ёмкость:** %s → %s' % (
                head.get('capacity_note') or g(head.get('capacity')) or '—',
                verdict(s, fnum(head.get('capacity'))) if fnum(head.get('capacity')) else '✅ спринт закрыт'),
            '> **Цель:** %s' % head.get('goal', '—'),
            '',
            '### План (в порядке запуска)',
            table(r),
            '',
            '### Ёмкость и прогресс',
            summary_lines(r, head),
            '',
        ]
        if head.get('_notes'):
            out += ['### Примечания и риски', head['_notes'], '']
        if head.get('kpi'):
            out += ['**KPI:** %s' % head['kpi'], '']
    return '\n'.join(out).rstrip() + '\n'




def lane_str(s):
    parts = []
    for ln in LANE_ORDER:
        if s['lanes'].get(ln):
            parts.append('%s %s' % (LANE_RU[ln], g(s['lanes'][ln])))
    return ' · '.join(parts) or '—'


def verdict(s, cap):
    if not cap:
        return '—'
    # «всего» — план всех дорожек к суммарной ёмкости всех дорожек (раньше делили на ёмкость dev → 100%+ враньё)
    total_cap = P.total_capacity()
    pct = round(100.0 * s['est'] / total_cap) if total_cap else 0
    dev = s['lanes'].get('dev', 0.0)
    dev_pct = round(100.0 * dev / cap)
    flag = '⚠️ перегруз' if dev_pct > 110 else ('🟡 плотно' if dev_pct > 95 else '🟢 запас')
    return '%s (dev-дорожка %d%%, все дорожки %d%%)' % (flag, dev_pct, pct)


def table(rows, with_link=True):
    out = ['| Код | Задача | Цель → KPI | Тип | FUNC | Оценка | Приор. | Зависит от | Статус |',
           '|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        code = str(r.get('code'))
        cell = '[[%s\\|%s]]' % (r['_file'], code) if with_link else code
        funcs = r.get('func', '').strip('[]')
        funcs = ', '.join(funcs.split(', ')).replace('FUNC-', '') if funcs else '—'
        deps = r.get('depends_on', '').strip('[]').replace('"', '')
        carried = r.get('carried_from')
        if carried:
            deps = (deps + (' ' if deps else '') + '⤴%s' % carried).strip()
        out.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            cell, r.get('title', ''), r.get('goal', ''), r.get('type', ''),
            funcs or '—', g(r.get('est')), r.get('priority', ''), deps or '—',
            ST_EMOJI.get(r.get('status', ''), r.get('status', ''))))
    return '\n'.join(out)


def summary_lines(rows, head):
    s = stat(rows)
    cap = fnum(head.get('capacity')) or P.lane_cap_total('dev')
    lines = ['- **Задач:** %d · **план:** %s чел-дней (%s)' % (s['n'], g(s['est']), lane_str(s))]
    lines.append('- **Ёмкость dev-дорожки:** %s → вердикт: %s' % (
        head.get('capacity_note') or ('%g' % cap), verdict(s, cap)))
    st = ' · '.join('%s %d' % (ST_EMOJI.get(k, k), v)
                    for k, v in sorted(s['status'].items(), key=lambda kv: kv[0]))
    lines.append('- **Прогресс:** %s' % (st or '—'))
    load = []
    for who in sorted(set(r.get('assignee', '') for r in rows)):
        if not who:
            continue
        ln = lane_of(who)
        name = P.lane_of(who)[1].split(',')[0]
        e = load_of(rows, who)
        pct = round(100.0 * e / LANE_CAP.get(ln, 15)) if LANE_CAP.get(ln) else 0
        load.append('%s %s/%s чел-дней (%d%%)%s' % (
            name, g(e), LANE_CAP.get(ln, 15), pct, ' ⚠️' if pct > 110 else ''))
    lines.append('- **Загрузка по агентам:** ' + ' · '.join(load))
    dep = [r for r in rows if r.get('carried_from')]
    if dep:
        lines.append('- **Переносы в этот спринт:** ' + ', '.join(
            '%s ← %s' % (r['code'], r['carried_from']) for r in dep))
    return '\n'.join(lines)


if __name__ == '__main__':
    sys.exit(main())
