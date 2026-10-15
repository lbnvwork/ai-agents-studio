#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Профиль проекта для toolkit: данные читаются из ядра или проектного слоя.

Как ищутся данные (первое сработавшее):
  1) аргументы --project / --layer / --core (если скрипт их принимает);
  2) окружение AGENTS_PROJECT / AGENTS_LAYER / AGENTS_CORE;
  3) файл `.agents` (генерирует setup.sh) рядом со скриптом, в каталоге скриптов
     или в корне docs; содержимое: CORE=…, PROJECT=…, LAYER=…;
  4) автоопределение: если в <core>/profiles ровно один рабочий профиль — берём его.

Публичное API: load(...) -> Project. Данные и производные — в docstring класса.
Модуль кладётся рядом со скриптами (setup.sh копирует проект + скрипты в docs).
"""
import argparse
import glob
import io
import os

CONFIG_NAME = '.agents'

# Тип задачи → дорожка (по умолчанию; профиль перекрывает ключом TASK_LANE)
DEFAULT_TASK_LANE = {
    'infra': 'devops', 'test': 'test', 'doc': 'pm',
    'planning': 'analytics', 'analysis': 'analytics',
}


def parse_env_file(path):
    """KEY=VALUE, по строке на ключ; комментарии и кавычки — как в shell-профиле."""
    data = {}
    for raw in io.open(path, encoding='utf-8'):
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, val = line.split('=', 1)
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in '\"\'':
            val = val[1:-1]
        data[key] = val
    return data


def _find_config(start_dir):
    """Ищет .agents вверх от каталога скрипта (до 4 уровней)."""
    d = os.path.abspath(start_dir)
    for _ in range(4):
        p = os.path.join(d, CONFIG_NAME)
        if os.path.isfile(p):
            return parse_env_file(p)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return {}


def docs_root(script_file):
    """Корень docs по расположению скрипта: <docs>/09-Служебное/Скрипты/x.py."""
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(script_file)), '..', '..'))


def add_args(parser):
    """Добавляет в argparse общие ключи профиля."""
    parser.add_argument('--core', help='каталог ядра (ai-agents-studio)')
    parser.add_argument('--project', help='имя профиля в ядре (profiles/<имя>)')
    parser.add_argument('--layer', help='каталог проектного слоя (project.env + roles/ + skills/)')
    return parser


def split_argv(argv, start_dir=None):
    """Вынимает --core/--project/--layer из argv скриптов без argparse."""
    known, rest = {}, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--core', '--project', '--layer') and i + 1 < len(argv):
            known[a.lstrip('-')] = argv[i + 1]
            i += 2
            continue
        rest.append(a)
        i += 1
    return load(project=known.get('project'), layer=known.get('layer'),
                core=known.get('core'), start_dir=start_dir), rest


def load(project=None, layer=None, core=None, start_dir=None):
    """Возвращает Project. Порядок источников см. в docstring модуля."""
    cfg = _find_config(start_dir or os.path.dirname(os.path.abspath(__file__)))
    project = project or os.environ.get('AGENTS_PROJECT') or cfg.get('PROJECT')
    layer = layer or os.environ.get('AGENTS_LAYER') or cfg.get('LAYER')
    core = core or os.environ.get('AGENTS_CORE') or cfg.get('CORE')

    if layer:
        profile = os.path.join(layer, 'project.env')
        if not os.path.isfile(profile):
            raise SystemExit('проектный слой без project.env: %s' % profile)
        return Project(parse_env_file(profile), core or '', profile)

    if not core:
        raise SystemExit(
            'не найден каталог ядра: задай --core, переменную AGENTS_CORE или файл .agents '
            '(его генерирует setup.sh)')
    profiles = sorted(glob.glob(os.path.join(core, 'profiles', '*', 'project.env')))
    if project:
        profile = os.path.join(core, 'profiles', project, 'project.env')
        if not os.path.isfile(profile):
            raise SystemExit('нет профиля: %s' % profile)
        return Project(parse_env_file(profile), core, profile)
    if len(profiles) == 1:
        return Project(parse_env_file(profiles[0]), core, profiles[0])
    if not profiles:
        raise SystemExit('в %s/profiles нет ни одного профиля' % core)
    raise SystemExit('профилей несколько — укажи --project (доступны: %s)' %
                     ', '.join(os.path.basename(os.path.dirname(p)) for p in profiles))


class Project(object):
    """Данные проекта из профиля + производные удобства.

    .name .title .kind .root .prefix            — идентификация
    .agents  — список агентов в порядке конвейера (dict: dir code lane title short does stem ports)
    .lanes   — {дорожка: {'cap': int|None, 'ru': str}}; .lane_order — порядок из LANES
    .awaiting — {значение: {'type':…, 'ref':…}}; .awaiting_type(value)
    .task_lane — {тип задачи: дорожка}; .reviewer — каталог агента-ревьюера (дорожка lead)
    .cur_sprint .sprint_from .sprint_to .stages .deadline_d1 .deadline_d2 .sprint_days
    .hours_per_day .archive_periods .docker .repos .prod_data_dir
    Методы: agent_by_dir/agent_by_code/agents_in_lane/lane_of/short/title_of/code_of_dir
    """

    def __init__(self, data, core, profile_path):
        self.data = data
        self.core = core
        self.profile_path = profile_path
        self.name = data.get('PROJECT', '')
        self.title = data.get('PROJECT_TITLE') or self.name
        self.kind = data.get('PROJECT_KIND') or 'web'
        self.root = data.get('AGENTS_ROOT', '')
        self.prefix = data.get('AGENT_PREFIX', '')
        self.agents = self._agents()
        self.lanes = self._lanes()
        self.lane_order = list(self.lanes.keys())
        self.awaiting = self._awaiting()
        self.task_lane = dict(DEFAULT_TASK_LANE)
        for item in _split_items(data.get('TASK_LANE', '')):
            if ':' in item:
                k, v = item.split(':', 1)
                self.task_lane[k.strip()] = v.strip()
        self.cur_sprint = _int(data.get('CUR_SPRINT')) or 0
        self.sprint_from = _int(data.get('SPRINT_FROM')) or 1
        self.sprint_to = _int(data.get('SPRINT_TO')) or self.cur_sprint
        self.stages = [s.strip() for s in data.get('STAGES', '').split(',') if s.strip()]
        self.deadline_d1 = data.get('DEADLINE_D1', '')
        self.deadline_d2 = data.get('DEADLINE_D2', '')
        self.sprint_days = _int(data.get('SPRINT_DAYS')) or 0
        self.hours_per_day = _int(data.get('HOURS_PER_DAY')) or 8
        self.archive_periods = {}
        for item in _split_items(data.get('ARCH_PERIOD', '')):
            if ':' in item:
                k, v = item.split(':', 1)
                self.archive_periods[k.strip()] = v.strip()
        self.docker = {k: data.get('DOCKER_' + k.upper(), '') for k in ('prefix', 'pm', 'dev', 'prod')}
        self.prod_data_dir = data.get('PROD_DATA_DIR', '')
        self.repos = {k: data.get(k, '') for k in ('CODE_REPO', 'DOCS_REPO', 'PM_DIR')}
        self.owner_code = data.get('OWNER_CODE', '') or 'owner'
        self.owner_title = data.get('OWNER_TITLE', '') or 'Руководитель'
        self.min_plan_sprint = _int(data.get('MIN_PLAN_SPRINT')) or 5
        self.archive_to = _int(data.get('ARCHIVE_TO')) or self.sprint_from
        self.deadline_d1_note = data.get('DEADLINE_D1_NOTE', '')
        self.deadline_d2_note = data.get('DEADLINE_D2_NOTE', '')
        self._by_dir = {a['dir']: a for a in self.agents}
        self._by_code = {a['code']: a for a in self.agents}

    # --- разбор профиля ----------------------------------------------------
    def _agents(self):
        out = []
        for pair in self.data.get('AGENTS', '').split():
            parts = pair.split(':')
            if len(parts) < 3:
                continue
            d, code, lane = parts[0], parts[1], parts[2]
            title = self.data.get('AGENT_TITLE_' + code.upper(), '')
            m = title[title.find('(') + 1:title.rfind(')')] if '(' in title else ''
            stem = self.data.get('AGENT_STEM_' + code.upper(), '') or code
            out.append({
                'dir': d, 'code': code, 'lane': lane, 'title': title,
                'short': self.data.get('AGENT_SHORT_' + code.upper(), '') or code,
                'does': self.data.get('AGENT_DOES_' + code.upper(), ''),
                'stem': stem, 'role': m,
                'ports': {k: self.data.get('PORT_%s_%s' % (stem.upper(), k), '')
                          for k in ('APP', 'DB', 'WEB')},
                'path': os.path.join(self.data.get('AGENTS_ROOT', ''), d),
            })
        return out

    def _lanes(self):
        out = {}
        for item in _split_items(self.data.get('LANES', '')):
            parts = item.split(':')
            if len(parts) < 2:
                continue
            lane = parts[0].strip()
            cap = _int(parts[1]) if len(parts) > 1 else None
            ru = parts[2].strip() if len(parts) > 2 else lane
            out[lane] = {'cap': cap, 'ru': ru}
        return out

    def _awaiting(self):
        out = {}
        for item in _split_items(self.data.get('AWAITING', '')):
            parts = item.split(':')
            val = parts[0].strip()
            out[val] = {'type': parts[1].strip() if len(parts) > 1 else 'lane',
                        'ref': parts[2].strip() if len(parts) > 2 else ''}
        return out

    # --- удобства ----------------------------------------------------------
    def agent_by_dir(self, d):
        return self._by_dir.get(d)

    def agent_by_code(self, code):
        return self._by_code.get(code)

    def code_of_dir(self, d):
        a = self._by_dir.get(d)
        return a['code'] if a else d

    def agents_in_lane(self, lane):
        return [a['dir'] for a in self.agents if a['lane'] == lane]

    def lane_of(self, d):
        """(дорожка, «Имя, роль») — для витрин загрузки."""
        a = self._by_dir.get(d)
        if a:
            return a['lane'], '%s, %s' % (a['short'], a['role'] or a['lane'])
        return (self.lane_order[0] if self.lane_order else 'pm'), d

    def short(self, d):
        a = self._by_dir.get(d)
        return a['short'] if a else d

    def title_of(self, code):
        a = self._by_code.get(code)
        return a['title'] if a else code

    def awaiting_type(self, value):
        return self.awaiting.get(value, {}).get('type', '')

    @property
    def reviewer(self):
        for lane in ('lead', 'pm'):
            who = self.agents_in_lane(lane)
            if who:
                return who[0]
        return ''

    @property
    def docs(self):
        return os.path.join(self.root, self.repos.get('PM_DIR', ''), 'docs')

    def lane_caps(self):
        return {k: (v['cap'] or 0) for k, v in self.lanes.items()}

    def lane_cap_total(self, lane):
        """Ёмкость дорожки = ёмкость × число её агентов."""
        return (self.lanes.get(lane, {}).get('cap') or 0) * len(self.agents_in_lane(lane))

    def comment_authors(self):
        """{код: «Имя (роль)»} для каналов комментариев: агенты + владелец."""
        out = {a['code']: a['title'] or a['code'] for a in self.agents}
        out[self.owner_code] = self.owner_title
        return out

    def total_capacity(self):
        return sum(v['cap'] or 0 for v in self.lanes.values())


def _split_items(value):
    return [x for x in (value or '').split() if x]


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None
