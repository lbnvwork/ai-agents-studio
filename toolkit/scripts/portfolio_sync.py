#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Портфельная витрина студии: собирает данные проектов в один дашборд.

Источник данных — «01-Портфель/Реестр проектов.md» (таблица: проект · ПМ · доки · профиль · код · контуры).
По каждому проекту читает: его профиль (CUR_SPRINT, OWNER_CODE), статьи спринта (status/est/awaiting),
шапку спринта (даты), Канбан, «Решения и риски», git-состояние доков и кода, docker-стеки машины.

Запуск (из docs/09-Служебное/Скрипты):
  python3 portfolio_sync.py --write   # пересобрать «Дашборд студии» и AUTO-блоки
  python3 portfolio_sync.py --check   # проверка реестра и доступности проектов
  (без ключей — печатает дашборд)
"""
import glob
import io
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import project as proj  # noqa: E402 — общий модуль toolkit

P, ARGV = proj.split_argv(sys.argv[1:], os.path.dirname(os.path.abspath(__file__)))
DOCS = proj.docs_root(__file__)
PORTFOLIO = os.path.join(DOCS, '01-Портфель')
REGISTRY = os.path.join(PORTFOLIO, 'Реестр проектов.md')
DASHBOARD = os.path.join(PORTFOLIO, 'Дашборд студии.md')


def sh(cmd, cwd=None):
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=20)
        return out.stdout.strip()
    except Exception:
        return ''


def frontmatter(path):
    text = io.open(path, encoding='utf-8').read()
    m = re.match(r'^---\n(.*?)\n---', text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).split('\n'):
        mm = re.match(r'^([a-z_]+):\s*(.*)$', line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    return fm, text[m.end():]


def parse_registry():
    """Таблица реестра → список проектов."""
    if not os.path.isfile(REGISTRY):
        return None  # это скрипт студийного уровня: реестра проектов в проекте нет
    rows, head = [], None
    for line in io.open(REGISTRY, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if set(''.join(cells)) <= set('-: '):
            continue
        if cells[0].lower() == 'проект':
            head = cells
            continue
        if head is None or len(cells) < 5:
            continue
        prof = cells[3]
        kind, _, pval = prof.partition(' ')
        code = []
        for item in cells[4].split(','):
            item = item.strip()
            if not item:
                continue
            pref, _, path = item.partition(':')
            if path and pref in ('api', 'app'):
                code.append((pref.strip(), path.strip()))
            else:
                code.append(('code', item))
        rows.append({'project': cells[0], 'pm': cells[1], 'docs': cells[2],
                     'profile_kind': kind.strip(), 'profile': pval.strip(),
                     'code': code, 'contours': [c.strip() for c in cells[5].split(',') if c.strip()]})
    return rows


def profile_env(entry):
    if entry['profile_kind'] == 'layer':
        path = os.path.join(entry['profile'], 'project.env')
    else:
        path = os.path.join(P.core, 'profiles', entry['profile'], 'project.env')
    return proj.parse_env_file(path) if os.path.isfile(path) else {}


def sprint_tasks(docs, sprint):
    base = os.path.join(docs, '03-Задачи/Спринты/Спринт-%02d' % sprint)
    out = []
    for path in sorted(glob.glob(os.path.join(base, '*.md'))):
        fm, _ = frontmatter(path)
        if fm.get('code'):
            fm['_file'] = os.path.basename(path)[:-3]
            out.append(fm)
    return out


def sprint_head(docs, sprint):
    path = os.path.join(docs, '03-Задачи/Планы спринтов/Спринт-%02d.md' % sprint)
    return frontmatter(path)[0] if os.path.isfile(path) else {}


def risks_count(docs):
    path = os.path.join(docs, '09-Служебное/Решения и риски.md')
    if not os.path.isfile(path):
        return 0, 0
    text = io.open(path, encoding='utf-8').read()
    def block(name):
        m = re.search(r'^## %s\n(.*?)(?=\n## |\Z)' % re.escape(name), text, re.S | re.M)
        return len([l for l in (m.group(1).split('\n') if m else []) if l.startswith('- ')])
    return block('Активные риски'), block('Открытые вопросы к руководителю')


def kanban_counts(docs):
    path = os.path.join(docs, '03-Задачи/Канбан.md')
    if not os.path.isfile(path):
        return {}
    col, out = None, {}
    for line in io.open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if line.startswith('## '):
            col = line[3:].strip()
        elif line.startswith('- [ ]') and col:
            out[col] = out.get(col, 0) + 1
    return out


def git_state(path):
    if not os.path.isdir(os.path.join(path, '.git')):
        return None
    dirty = len([l for l in sh(['git', '-C', path, 'status', '--porcelain']).split('\n') if l])
    ahead = sh(['git', '-C', path, 'rev-list', '--count', '@{u}..HEAD'])
    return {'dirty': dirty, 'ahead': int(ahead) if ahead.isdigit() else 0,
            'branch': sh(['git', '-C', path, 'branch', '--show-current']) or '—'}


def stat_project(entry):
    env = profile_env(entry)
    docs = entry['docs']
    cur = int((env.get('CUR_SPRINT') or '0').strip() or 0)
    owner = env.get('OWNER_CODE', 'max')
    tasks = sprint_tasks(docs, cur)
    done = [t for t in tasks if t.get('status') in ('done', 'cancelled')]
    live = [t for t in tasks if t.get('status') not in ('done', 'cancelled')]
    est = sum(float(t.get('est') or 0) for t in tasks)
    est_done = sum(float(t.get('est') or 0) for t in done)
    wait_me = [t for t in live if t.get('awaiting') == owner]
    wait_agents = [t for t in live if t.get('awaiting') and t.get('awaiting') not in (owner, '—')]
    risks, questions = risks_count(docs)
    repos = [('docs', docs)] + [(pref, path) for pref, path in entry['code']]
    gits = [(name, git_state(path)) for name, path in repos]
    dirty = sum(g['dirty'] for _, g in gits if g)
    ahead = sum(g['ahead'] for _, g in gits if g)
    head = sprint_head(docs, cur)
    return {'entry': entry, 'cur': cur, 'tasks': len(tasks), 'live': len(live), 'done': len(done),
            'est': est, 'est_done': est_done, 'wait_me': wait_me, 'wait_agents': wait_agents,
            'risks': risks, 'questions': questions, 'gits': gits, 'dirty': dirty, 'ahead': ahead,
            'head': head, 'kanban': kanban_counts(docs)}


def verdict(s):
    if s['ahead'] or s['dirty']:
        return '🟡 git-гигиена'
    if s['wait_me']:
        return '🟡 ждёт руководителя'
    if not s['tasks']:
        return '⬜ нет данных'
    return '🟢'


def portfolio_table(stats):
    out = ['| Проект | Спринт | Сроки | Задач | Готово, чел-дни | Ждёт меня | Ждут агентов | Риски | Статус |',
           '|---|---|---|---|---|---|---|---|---|']
    for s in stats:
        h = s['head']
        term = '%s — %s' % (h.get('start', '—'), h.get('end', '—')) if h else '—'
        out.append('| **%s** | %s | %s | %d (%d закрыто) | %s / %s | %d | %d | %d+%d | %s |' % (
            s['entry']['project'], s['cur'], term, s['tasks'], s['done'],
            ('%g' % s['est_done']) if s['est_done'] else '0', ('%g' % s['est']) if s['est'] else '0',
            len(s['wait_me']), len(s['wait_agents']), s['risks'], s['questions'], verdict(s)))
    return '\n'.join(out)


def me_block(stats):
    lines = ['| Проект | Задача | Статус | Чего ждёт |', '|---|---|---|---|']
    for s in stats:
        for t in s['wait_me']:
            lines.append('| %s | %s | %s | %s |' % (s['entry']['project'], t.get('code'), t.get('status'),
                                                     t.get('title', '')[:70]))
    return '\n'.join(lines) if len(lines) > 2 else '— мяч у меня не держат —'


def agents_block(stats):
    lines = ['| Проект | Ждёт | Задач | Коды |', '|---|---|---|---|']
    for s in stats:
        by = {}
        for t in s['wait_agents']:
            by.setdefault(t.get('awaiting'), []).append(t.get('code'))
        for who, codes in sorted(by.items()):
            lines.append('| %s | %s | %d | %s |' % (s['entry']['project'], who, len(codes), ', '.join(codes)))
    return '\n'.join(lines) if len(lines) > 2 else '— никто не держит —'


def resources_block(stats):
    stacks = [l for l in sh(['docker', 'compose', 'ls']).split('\n') if l and not l.startswith('NAME')]
    mem = sh(['free', '-h'])
    mem_line = [l for l in mem.split('\n') if l.lower().startswith('mem')]
    out = ['**Docker-стеки (запущено):** %s' % ('; '.join(stacks) if stacks else '— ничего не запущено —'), '']
    if mem_line:
        out.append('```\n%s\n```' % mem_line[0])
    out += ['', '| Проект | git: правок | git: не запушено | Ветки |', '|---|---|---|---|']
    for s in stats:
        branches = ', '.join('%s:%s' % (n, g['branch']) for n, g in s['gits'] if g)
        out.append('| %s | %d | %d | %s |' % (s['entry']['project'], s['dirty'], s['ahead'], branches))
    return '\n'.join(out)


def registry_table(stats):
    out = ['| Проект | ПМ (воркспейс) | Контуры | Доки |', '|---|---|---|---|']
    for s in stats:
        e = s['entry']
        out.append('| %s | `%s` | %s | `%s` |' % (e['project'], e['pm'], ', '.join(e['contours']) or '—', e['docs']))
    return '\n'.join(out)


def refresh_region(name, content):
    if not os.path.isfile(DASHBOARD):
        return False
    text = io.open(DASHBOARD, encoding='utf-8').read()
    pat = re.compile(r'(<!-- AUTO:%s -->\n)(.*?)(<!-- /AUTO:%s -->)' % (name, name), re.S)
    m = pat.search(text)
    if not m:
        return False
    new = m.group(1) + '\n' + content + '\n\n' + m.group(3)
    if new == m.group(0):
        return False
    io.open(DASHBOARD, 'w', encoding='utf-8').write(text[:m.start()] + new + text[m.end():])
    return True


def write_all(stats):
    if not os.path.isfile(DASHBOARD):
        io.open(DASHBOARD, 'w', encoding='utf-8').write(doc_skeleton())
        print('создан: %s' % os.path.basename(DASHBOARD))
    for name, content in (('PORTFOLIO', portfolio_table(stats)), ('ME', me_block(stats)),
                          ('AGENTS', agents_block(stats)), ('RESOURCES', resources_block(stats)),
                          ('REGISTRY', registry_table(stats))):
        ok = refresh_region(name, content)
        print('  блок %s: %s' % (name, 'ok' if ok else '—'))


def doc_skeleton():
    return '''# Дашборд студии\n\n> **Файл генерируется** — правки не сохранятся. Обновить: `python3 09-Служебное/Скрипты/portfolio_sync.py --write`.\n> Источники: [[Реестр проектов]] + доки и репозитории проектов + docker на машине.\n\n## 1. Портфель: проекты, спринты, мяч\n\n<!-- AUTO:PORTFOLIO -->\n<!-- /AUTO:PORTFOLIO -->\n\n## 2. Что ждёт руководителя\n\n<!-- AUTO:ME -->\n<!-- /AUTO:ME -->\n\n## 3. Что ждут агенты (по проектам)\n\n<!-- AUTO:AGENTS -->\n<!-- /AUTO:AGENTS -->\n\n## 4. Ресурсы и git-гигиена\n\n<!-- AUTO:RESOURCES -->\n<!-- /AUTO:RESOURCES -->\n\n## 5. Реестр проектов\n\n<!-- AUTO:REGISTRY -->\n<!-- /AUTO:REGISTRY -->\n'''


def check(rows):
    problems = []
    for e in rows:
        if not os.path.isdir(e['docs']):
            problems.append('%s: нет доков %s' % (e['project'], e['docs']))
        env = profile_env(e)
        if not env:
            problems.append('%s: не прочитан профиль (%s %s)' % (e['project'], e['profile_kind'], e['profile']))
        for pref, path in e['code']:
            if not os.path.isdir(path):
                problems.append('%s: нет репозитория кода %s (%s)' % (e['project'], pref, path))
    print('проверено проектов: %d' % len(rows))
    if problems:
        print('нарушений: %d' % len(problems))
        for p in problems:
            print(' - ' + p)
        return 1
    print('нарушений нет')
    return 0


def main():
    if not os.path.isfile(REGISTRY):
        print('portfolio_sync: скрипт студийного уровня — нужен «01-Портфель/Реестр проектов.md».')
        print('Запускается в доках студии (lazurit-docs), не в проекте. Пропуск.')
        return 0
    rows = parse_registry()
    if '--check' in ARGV:
        return check(rows)
    stats = [stat_project(e) for e in rows]
    if '--write' in ARGV:
        write_all(stats)
        return 0
    print(portfolio_table(stats))
    return 0


if __name__ == '__main__':
    sys.exit(main())
