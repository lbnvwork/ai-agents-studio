#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разовый импорт плана в данные: проставляет est/order/goal/carried_from в существующие
статьи и создаёт статьи-заготовки под коды плана. Шаблон заготовки — из профиля проекта
(profiles/<проект>/templates/task_stub.md).

Запуск (из docs/09-Служебное/Скрипты):
  python3 plan_import.py --write /tmp/plan.json    # таблицы плана → данные
  python3 plan_apply.py                            # dry-run: что будет сделано
  python3 plan_apply.py --apply                    # запись

Ключи: --plan PATH (JSON из plan_import.py, по умолчанию /tmp/plan.json), --apply,
--today ГГГГ-ММ-ДД (дата `updated` в заготовках; по умолчанию — сегодня по МСК),
--status (статус заготовок, по умолчанию spec), --moves FILE (разовые исключения:
{"renumber": {"5.8": ["6.8", "5.8"]}, "drop": {"7.8": ["12.5", "7.8"]}}), плюс
общие --core/--project/--layer.

Проектные данные берутся из профиля (см. toolkit/project.py): исполнитель заготовки —
TASK_LANE (тип задачи → дорожка), иначе пул дорожки dev; ревьюер — агент дорожки lead.
"""
import datetime
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
TASKS = os.path.join(DOCS, '03-Задачи/Спринты')
PLAN_JSON = '/tmp/plan.json'   # вход: данные из plan_import.py
TODAY = datetime.date.today().isoformat()
STATUS = 'spec'
RENUMBERS = {}   # {"старый код": ["новый код", "carried_from"]} — переносы (--moves)
DROPS = {}       # {"код": ["новый код", "carried_from"]} — не заводить статью (--moves)

TAIL = re.compile(r'\s*—\s*(перенос|перенесена|перенесён|отложен).*$')
DEV = P.agents_in_lane('dev')   # пул разработки: тип задачи без дорожки → наименее загруженный
TRANS = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh',
         'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
         'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
         'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e',
         'ю': 'yu', 'я': 'ya'}


def clean(text):
    t = text.replace('**', '').replace('`', '')
    return re.sub(r'\s+', ' ', t).strip()


def title_of(text):
    """Название без хвоста «— перенос из спринта N»."""
    t = clean(text)
    t = TAIL.sub('', t).strip().rstrip('—').strip()
    return t


def slug(text):
    words = re.findall(r'[А-Яа-яЁёA-Za-z0-9]+', text)[:4]
    out = []
    for w in words:
        s = ''.join(TRANS.get(ch.lower(), ch.lower()) for ch in w)
        out.append(re.sub(r'[^a-z0-9]', '', s))
    return '_'.join(x for x in out if x)[:48]


def size_from_est(est):
    if est is None:
        return 'M'
    return 'S' if est <= 1 else ('M' if est <= 2 else 'L')


def filename(code, title):
    t = title_of(title)
    t = re.sub(r'[«»"“”]', '', t)
    t = t.replace('/', '-').replace('\\', '-').replace(':', '').replace('?', '')
    t = re.sub(r'\s+', ' ', t).strip().rstrip('.')
    return '%s. %s.md' % (code, t)


def read_fm(text):
    m = re.match(r'^---\n(.*?)\n---', text, re.S)
    if not m:
        return None, text
    return m.group(1).split('\n'), text[m.end():]


def patch_fm(path, fields_after_size, fields_after_depends):
    """Вставить поля в frontmatter, сохранив остальное байт-в-байт."""
    text = io.open(path, encoding='utf-8').read()
    lines, rest = read_fm(text)
    if lines is None:
        return False, 'нет frontmatter'
    new_keys = set(k for k, _ in fields_after_size) | set(k for k, _ in fields_after_depends)
    keep = []
    for ln in lines:
        mm = re.match(r'^([a-z_]+):', ln)
        if mm and mm.group(1) in new_keys:
            continue
        keep.append(ln)
    lines = keep

    def rebuild_keys(ls):
        ks = {}
        for i, ln in enumerate(ls):
            mm = re.match(r'^([a-z_]+):', ln)
            if mm and mm.group(1) not in ks:
                ks[mm.group(1)] = i
        return ks

    def anchor(ks, *names):
        for n in names:
            if n in ks:
                return ks[n]
        return len(lines) - 1

    keys = rebuild_keys(lines)
    i = anchor(keys, 'size', 'priority', 'sprint')
    for k, v in reversed(fields_after_size):
        lines.insert(i + 1, '%s: %s' % (k, v))
    keys = rebuild_keys(lines)
    j = anchor(keys, 'depends_on', 'updated', 'awaiting')
    for k, v in reversed(fields_after_depends):
        lines.insert(j + 1, '%s: %s' % (k, v))
    out = '---\n' + '\n'.join(lines) + '\n---' + rest
    if out == text:
        return False, 'без изменений'
    io.open(path, 'w', encoding='utf-8').write(out)
    return True, 'ok'


def index_articles():
    idx = {}
    for base, dirs, files in os.walk(TASKS):
        if 'Архив' in base:
            continue
        for name in sorted(files):
            if not name.endswith('.md'):
                continue
            path = os.path.join(base, name)
            head = io.open(path, encoding='utf-8').read()[:400]
            m = re.search(r'^code:\s*"?([\d.]+)', head, re.M)
            if m:
                idx.setdefault(m.group(1), path)
    return idx


def stub(code, row, sprint, assignee):
    """Заготовка статьи по шаблону профиля (templates/task_stub.md)."""
    est = row['est'] if row['est'] is not None else 0
    funcs = ', '.join('FUNC-%s' % f.rstrip('*') for f in row['func'] if f.strip('*'))
    deps = row['depends_on']
    carried = row.get('carried_from')
    pm = P.lane_agent('pm')
    values = {
        'code': code,
        'title': title_of(row['title']).replace('"', ''),
        'type': row['type'],
        'status': STATUS,
        'assignee': assignee,
        'reviewer': P.reviewer,
        'sprint': sprint,
        'priority': row['priority'],
        'size': size_from_est(row['est']),
        'est': '%g' % est,
        'order': row['order'],
        'goal': clean(row['goal']),
        'awaiting': P.awaiting_none,
        'funcs': funcs,
        'funcs_or_dash': funcs or P.awaiting_none,
        'branch': '%d_%s' % (sprint, slug(row['title'])),
        'deps_fm': ', '.join('"%s"' % d for d in deps),
        'deps_or_dash': ', '.join(deps) or P.awaiting_none,
        'carried_from_line': 'carried_from: "%s"' % carried if carried else None,
        'updated': TODAY,
        'sprint_link': '[[Спринт-%02d|Спринт %d]]' % (sprint, sprint),
        'tz': P.data.get('STUB_TZ_FUNC' if row['func'] else 'STUB_TZ_PLAN', ''),
        'verification': P.data.get('STUB_VERIFICATION', ''),
        'pm_channel': P.title_of(P.agent_by_dir(pm)['code']) if pm else P.owner_title,
    }
    return P.render(P.template_path('task_stub.md'), values)


def main():
    argv = list(ARGV)

    def flag(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    global TODAY, STATUS, PLAN_JSON
    apply = '--apply' in argv
    TODAY = flag('--today', TODAY)
    STATUS = flag('--status', STATUS)
    PLAN_JSON = flag('--plan', PLAN_JSON)
    moves_path = flag('--moves')
    if moves_path:
        moves = json.load(io.open(moves_path, encoding='utf-8'))
        RENUMBERS.update(moves.get('renumber', {}))
        DROPS.update(moves.get('drop', {}))
    plan = json.load(io.open(PLAN_JSON, encoding='utf-8'))
    idx = index_articles()

    rows = []
    for sprint_s, data in sorted(plan.items(), key=lambda kv: int(kv[0])):
        sprint = int(sprint_s)
        for row in data['rows']:
            code = row['code']
            if code in DROPS:
                continue
            if code in RENUMBERS:
                new_code, carried = RENUMBERS[code]
                row = dict(row)
                row['code'] = new_code
                row['carried_from'] = carried
                code = new_code
            rows.append((sprint, code, row))

    # Исполнители существующих статей + их загрузка (est из плана).
    owner = {}
    for sprint, code, row in rows:
        if code in idx:
            head = io.open(idx[code], encoding='utf-8').read()[:600]
            m = re.search(r'^assignee:\s*(\S+)', head, re.M)
            if m:
                owner[code] = m.group(1)
    load = {}
    for sprint, code, row in rows:
        who = owner.get(code)
        if who in DEV:
            load[(sprint, who)] = load.get((sprint, who), 0) + (row['est'] or 0)

    assign = {}
    for sprint in sorted(set(s for s, _, _ in rows)):
        for _, code, row in [r for r in rows if r[0] == sprint]:
            if code in idx:
                continue
            lane_agent = P.agent_for_type(row['type'])
            if lane_agent:
                assign[code] = lane_agent
            else:
                dev = sorted(DEV, key=lambda d: (load.get((sprint, d), 0), d))[0]
                assign[code] = dev
                load[(sprint, dev)] = load.get((sprint, dev), 0) + (row['est'] or 0)

    created, patched, skipped, problems = [], [], [], []
    extra_carried = dict((dst, orig) for src, (dst, orig) in DROPS.items())
    for sprint, code, row in rows:
        est = row['est'] if row['est'] is not None else 0
        carried = row.get('carried_from') or extra_carried.get(code)
        after_size = [('est', '%g' % est), ('order', '%d' % row['order']),
                      ('goal', '"%s"' % clean(row['goal']))]
        after_dep = [('carried_from', '"%s"' % carried)] if carried else []
        if code in idx:
            if apply:
                changed, note = patch_fm(idx[code], after_size, after_dep)
                if changed:
                    patched.append(code)
                else:
                    skipped.append('%s (%s)' % (code, note))
            else:
                patched.append(code)
        else:
            path = os.path.join(TASKS, 'Спринт-%02d' % sprint, filename(code, row['title']))
            if os.path.exists(path):
                problems.append('файл уже есть: %s' % os.path.basename(path))
                continue
            if apply:
                row2 = dict(row)
                row2['carried_from'] = carried
                io.open(path, 'w', encoding='utf-8').write(stub(code, row2, sprint, assign[code]))
            created.append('%s → %s [%s]' % (code, os.path.basename(path), assign[code]))

    print('%s: заготовок %d, обновлено %d, без изменений %d' % (
        'ЗАПИСЬ' if apply else 'DRY-RUN', len(created), len(patched), len(skipped)))
    print('\n--- заготовки ---')
    for c in created:
        print(' +', c)
    print('\n--- frontmatter обновлён (%d) ---' % len(patched))
    print(' ', ', '.join(patched))
    if skipped:
        print('\n--- без изменений: %s' % ', '.join(skipped))
    if problems:
        print('\n--- проблемы (%d) ---' % len(problems))
        for p in problems:
            print(' !', p)
    print('\nнагрузка девов по спринтам (после распределения):')
    for sprint in sorted(set(s for s, _, _ in rows)):
        print('  спринт %-2d may=%4.1f jun=%4.1f' % (
            sprint, load.get((sprint, DEV[0]), 0), load.get((sprint, DEV[1]), 0)))


if __name__ == '__main__':
    main()
