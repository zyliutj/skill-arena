"""Local storage and report helpers. Standard library only; never calls a model."""
import argparse
from report_view import render as render_reader
import hashlib
import html
import json
import math
from pathlib import Path
import random
import re
import shutil
import uuid
from datetime import datetime, timezone


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', value):
        raise ValueError('ID must use lowercase letters, numbers and hyphens (1–64 chars)')
    if value.upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}:
        raise ValueError('Reserved filename')
    return value


def safe_child(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if path == root or root not in path.parents:
        raise ValueError('Path escapes its root')
    return path


def init(root):
    root = Path(root)
    for name in ('runs', 'tmp'):
        (root / name).mkdir(parents=True, exist_ok=True)
    if not (root / 'registry.json').exists():
        write(root / 'registry.json', {'schema_version': 1, 'skills': []})
    (root / 'history.jsonl').touch(exist_ok=True)


def register(root, record):
    required = ('id', 'name', 'source', 'version', 'tags', 'local_path', 'license')
    if any(k not in record for k in required) or not isinstance(record['tags'], list):
        raise ValueError('Record requires ' + ', '.join(required))
    identifier(record['id'])
    if 'scores' in record:
        record['selection_priority'] = selection_priority(record)
    db = read(Path(root) / 'registry.json')
    record['checked_at'] = stamp()
    db['skills'] = [s for s in db['skills'] if s['id'] != record['id']] + [record]
    write(Path(root) / 'registry.json', db)


def selection_gate(record):
    """Stars eligibility for new selections; never re-rank historical outputs."""
    state = record.get('stars_status', 'unknown')
    if state not in {'known', 'unknown', 'not_applicable'}:
        raise ValueError('Invalid stars status')
    specified = record.get('user_specified', False)
    if type(specified) is not bool:
        raise ValueError('user_specified must be boolean')
    if specified and not str(record.get('user_specified_evidence', '')).strip():
        raise ValueError('User exception requires an explicit request reference')
    if state == 'known':
        stars = record.get('stars')
        if type(stars) is not int or stars < 0 or not record.get('stars_checked_at'):
            raise ValueError('Known stars require nonnegative integer and check date')
    if record.get('kind') == 'baseline':
        return {'eligible': True, 'reason': 'baseline'}
    if specified:
        return {'eligible': True, 'reason': 'user-specified exception'}
    if state == 'known':
        return {'eligible': stars >= 500, 'reason': 'stars >= 500' if stars >= 500 else 'stars < 500'}
    github = str(record.get('source', '')).startswith(('https://github.com/', 'http://github.com/')) or bool(record.get('repository'))
    if state == 'not_applicable' and not github:
        return {'eligible': True, 'reason': 'stars not applicable'}
    return {'eligible': False, 'reason': 'stars pending verification'}


def check_selection(path):
    candidates = read(path)['candidates']
    failures = []
    for record in candidates:
        if record.get('status') == 'selected':
            gate = selection_gate(record)
            if not gate['eligible']: failures.append(str(record['id']) + ': ' + gate['reason'])
    if failures: raise ValueError('Selection blocked: ' + '; '.join(failures))
    return {'status': 'passed'}


def selection_priority(record):
    """Selection heuristic only. Never used for judging output quality."""
    weights = {'task_fit': 35, 'workflow': 25, 'compatibility': 15, 'maintenance': 10}
    scores = record['scores']
    for key in weights:
        value = scores.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 5:
            raise ValueError('Invalid selection score: ' + key)
    total = sum(weights[k] * scores[k] / 5 for k in weights)
    state = record.get('stars_status', 'unknown')
    if state not in {'known', 'unknown', 'not_applicable'}:
        raise ValueError('Invalid stars status')
    star_score = None
    if state == 'known':
        stars = record.get('stars')
        if type(stars) is not int or stars < 0 or not record.get('stars_checked_at'):
            raise ValueError('Known stars require nonnegative integer and check date')
        star_score = min(5, math.log10(1 + stars))
        total += 15 * star_score / 5
    else:
        total = total * 100 / 85
    return {'total': round(total, 2), 'star_score': star_score,
            'provisional': state == 'unknown', 'stars_status': state, 'eligibility': selection_gate(record)}


def candidate_overview(run, mapping):
    """Use run-frozen metadata, with transparent fallback for historical runs."""
    run = Path(run)
    metadata = {}
    discovery = run / 'discovery.json'
    if discovery.exists():
        metadata = {x['id']: x for x in read(discovery).get('candidates', [])}
    lines = ['## 本轮用了哪些候选？', '', '筛选优先级不参与结果质量评分；stars属于来源仓库。', '']
    cards = ['<section><h2>本轮用了哪些候选？</h2><p>筛选优先级不参与结果质量评分；stars属于来源仓库。</p>']
    for item in mapping.values():
        ident = identifier(item['id'])
        data = {**metadata.get(item.get('skill_id') or ident, {}), **item}
        baseline = item.get('kind') == 'baseline' or ident == 'baseline'
        lines += ['### ' + candidate_label(item), '']
        cards.append('<h3>' + html.escape(candidate_label(item)) + '</h3>')
        execution = run / 'variants' / ident / 'execution.json'
        log = read(execution) if execution.exists() else {}
        star_state = data.get('stars_status', 'unknown')
        stars = (str(data.get('stars')) + '（' + str(data.get('stars_checked_at', '未记录日期')) + '）'
                 if star_state == 'known' else '不适用' if star_state == 'not_applicable' or baseline else '未记录/未核验')
        values = {'比较单位': '普通提示词基线' if baseline else data.get('candidate_type', '未记录'),
                  '来源仓库': data.get('repository', '未记录'), 'stars / 查询日期': stars,
                  '固定版本': data.get('version', '未记录'), '入选理由': data.get('reason', data.get('fit_reason', '未记录')),
                  '实际模块': log.get('modules_used', data.get('modules_used', '未记录')),
                  '主要限制': data.get('limitations', '未记录')}
        if 'scores' in data:
            priority = selection_priority(data)
            values['筛选优先级'] = str(priority['total']) + ('（暂定，stars缺失）' if priority['provisional'] else '')
        for key, value in values.items():
            value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
            lines.append('- ' + key + '：' + value.replace('\n', ' '))
            cards.append('<p><b>' + key + '</b>：' + html.escape(value) + '</p>')
        links = []
        source = data.get('source', '')
        if isinstance(source, str) and source.startswith(('https://', 'http://')):
            links.append(('原始来源', source))
        snapshot_id = identifier(item.get('skill_id') or ident)
        snap = run / 'snapshots' / snapshot_id / 'SKILL.md'
        if snap.is_file(): links.append(('实际使用的 SKILL.md', snap.resolve().as_uri()))
        if execution.is_file(): links.append(('执行记录', execution.resolve().as_uri()))
        for label, url in links:
            cards.append('<p><a href="' + html.escape(url, quote=True) + '">' + label + '</a></p>')
            lines.append('- [' + label + '](<' + url + '>)')
        lines.append('')
    for path in (run / 'discovery.md', discovery):
        if path.is_file():
            url = path.resolve().as_uri()
            cards.append('<p><a href="' + url + '">' + path.name + '：完整调查与取舍</a></p>')
            lines.append('- [完整调查与取舍：' + path.name + '](<' + url + '>)')
    cards.append('</section>')
    return lines + [''], ''.join(cards)


def new_run(root, run_id):
    path = safe_child(Path(root) / 'runs', identifier(run_id))
    path.mkdir(parents=True, exist_ok=False)
    for name in ('inputs', 'variants', 'snapshots', 'evaluation'):
        (path / name).mkdir()
    (path / 'task.md').write_text('请在派发前写入冻结任务。\n', encoding='utf-8')
    write(path / 'rubric.json', {'weights': {'需求契合': 25, '事实与证据': 25, '方法逻辑': 25, '可执行性': 15, '表达交付': 10}, 'tie_threshold': 3})
    write(path / 'protocol.json', {'created_at': stamp(), 'status': 'draft', 'model': 'unknown', 'isolation': 'context-only', 'equal_budget': False, 'user_limits': None, 'network_policy': None, 'common_support_skills': [], 'retry_policy': 'one infrastructure retry; preserve attempts'})
    return path


def copy_tree(source, target):
    source = Path(source).resolve()
    target = Path(target).resolve()
    if target == source or source in target.parents:
        raise ValueError('Destination cannot be inside source')
    # Reject symlinks/junctions to prevent accidental capture outside the artifact.
    for p in [source, *source.rglob('*')]:
        if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
            raise ValueError('Linked paths must be materialized explicitly: ' + str(p))
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('.git', '__pycache__', '.env', '.env.*'))


def snapshot(run, skill_id, source):
    if not (Path(source) / 'SKILL.md').is_file():
        raise ValueError('Source must contain SKILL.md')
    target = safe_child(Path(run) / 'snapshots', identifier(skill_id))
    copy_tree(source, target)
    files = {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}
    write(Path(run) / 'snapshots' / (skill_id + '.manifest.json'), {'source': str(Path(source).resolve()), 'files': files, 'captured_at': stamp()})


def packet(run, manifest):
    run = Path(run)
    ids = [x['id'] for x in manifest]
    if len(set(ids)) != len(ids) or not ids or len(ids) > 26:
        raise ValueError('Expected 1–26 unique variants')
    for item in manifest:
        identifier(item['id'])
        source = safe_child(run / 'variants', item['id'])
        if not source.is_dir():
            raise ValueError('Missing variant: ' + item['id'])
    dest = run / 'judge-packet'
    dest.mkdir(exist_ok=False)
    order = list(manifest)
    random.SystemRandom().shuffle(order)
    mapping = {}
    for i, item in enumerate(order):
        alias = chr(65+i)
        # Only deliverables and sources; logs may reveal skill identity.
        target = dest / alias
        target.mkdir()
        for rel in item['artifacts']:
            src = safe_child(run / 'variants' / item['id'], rel)
            dst = safe_child(target, rel)
            if not src.is_file():
                raise ValueError('Artifact is not a file: ' + str(src))
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        mapping[alias] = item
    write(run / 'mapping.json', mapping)
    return mapping


def candidate_label(item, summary=''):
    name = item.get('display_name') or item.get('skill_id') or item['id']
    if item.get('kind') == 'baseline' or item['id'] == 'baseline':
        name = '普通提示词（无 skill）'
    return str(name) + (' — ' + ' '.join(summary.split())[:70] if summary else '')


def lowest_two(run):
    """Only eligible scored skills; a tie across the cutoff needs a human choice."""
    run = Path(run)
    mapping = read(run / 'mapping.json')
    ranking = read(run / 'ranking.json')['results']
    skills = []
    for row in ranking:
        item = mapping[row['id']]
        score = row.get('total')
        if (item.get('kind') != 'baseline' and item['id'] != 'baseline'
                and row['status'] == 'eligible' and type(score) in (int, float)
                and math.isfinite(score)):
            skills.append((score, item['id']))
    skills.sort()
    if len(skills) < 2:
        raise ValueError('Fewer than two scored eligible skills; choose removals by name')
    threshold = read(run / 'rubric.json').get('tie_threshold', 3)
    if len(skills) > 2 and skills[2][0] - skills[1][0] <= threshold:
        raise ValueError('Tie across removal cutoff; choose removals by name')
    return [item[1] for item in skills[:2]]


def interaction(run, rows, mapping):
    """Ready-to-use questions for the host's native choice/free-text tool."""
    candidates = [{'variant_id': mapping[r['id']]['id'], 'alias': r['id'],
                   'label': candidate_label(mapping[r['id']], r['summary'])} for r in rows]
    try:
        low = lowest_two(run)
        names = [candidate_label(next(v for v in mapping.values() if v['id'] == x)) for x in low]
        low_option = '移除评分最低的两款：' + '、'.join(names)
        reason = None
    except ValueError as exc:
        low, reason = None, str(exc)
        low_option = '查看评分后指定移除（存在并列或有效评分不足）'
    payload = {
        'run_id': Path(run).name,
        'action': {'questions': [{'title': '这些结果里有满意的吗？请选择下一步，也可直接输入你的要求。',
          'options': ['优化已有方案', '重做已有方案', '满意，接着做下一项任务', '都不满意，调整候选 skill', '先保留，暂不继续']}]},
        'selection': {'questions': [{'title': '使用哪些方案？单项可点选；多项请在输入框写出名称，并补充修改要求或下一项任务。',
          'options': [c['label'] for c in candidates]}]},
        'adjustment': {'questions': [
          {'title': '是否增加两款尚未尝试、适合当前任务的 skill？', 'options': ['增加 2 款新 skill', '不增加']},
          {'title': '下一轮移除哪些候选？只退出下一轮，历史文件保留；也可输入具体名称。',
           'options': ['保留现有候选', '我来指定移除的候选', low_option]}]},
        'candidates': candidates, 'lowest_two': low, 'lowest_two_unavailable_reason': reason,
        'dispatch': 'Coordinator calls available native question tool; this JSON does not render UI or authorize execution.'}
    write(Path(run) / 'interaction.json', payload)
    return payload


def report(run):
    run = Path(run)
    rubric = read(run / 'rubric.json')
    weights = rubric['weights']
    valid_number = lambda n: type(n) in (int, float) and math.isfinite(n)
    if not weights or any(not valid_number(w) or w <= 0 for w in weights.values()) or abs(sum(weights.values()) - 100) > 1e-6:
        raise ValueError('Positive finite weights must sum to 100')
    threshold = rubric.get('tie_threshold', 3)
    if not valid_number(threshold) or not 0 <= threshold <= 100:
        raise ValueError('Invalid tie threshold')
    mapping = read(run / 'mapping.json')
    rows = read(run / 'evaluation' / 'judge.json')['results']
    ids = [r['id'] for r in rows]
    if not rows or len(set(ids)) != len(ids) or set(ids) != set(mapping):
        raise ValueError('Judge must cover every anonymous ID exactly once')
    statuses = {'eligible', 'needs-review', 'disqualified', 'failed', 'blocked'}
    for r in rows:
        if r['status'] not in statuses:
            raise ValueError('Unknown status')
        for key in ('summary', 'strengths', 'weaknesses', 'best_for', 'uncertainty'):
            if not isinstance(r.get(key), str) or not r[key].strip():
                raise ValueError('Missing text field: ' + key)
        dims = r.get('dimensions', {})
        r['total'] = None
        if r['status'] == 'eligible' or dims:
            if set(dims) != set(weights):
                raise ValueError('Dimensions must exactly match rubric')
            for d in dims.values():
                n = d.get('score')
                if not valid_number(n) or not 0 <= n <= 5 or not isinstance(d.get('evidence'), str) or not d['evidence'].strip():
                    raise ValueError('Invalid score or missing evidence')
            r['total'] = sum(weights[k] * dims[k]['score'] / 5 for k in weights)
    rows.sort(key=lambda r: (r['status'] != 'eligible', -(r['total'] or 0), r['id']))
    anchor, rank = None, 0
    for index, r in enumerate(rows, 1):
        r['rank'] = None
        if r['status'] == 'eligible':
            if anchor is None or anchor - r['total'] > threshold:
                rank, anchor = index, r['total']
            r['rank'] = rank
    single = len(rows) == 1
    title = '方案质量检查' if single else 'Skill 对比报告'
    if single:
        rows[0]['rank'] = None
    overview_lines, _ = candidate_overview(run, mapping)
    lines = ['# ' + title, '', '方案编号固定，排名不作为选择编号。评分只适用于本次任务与版本；并列阈值不是统计置信区间。', ''] + overview_lines
    lines += ['| 方案 | 排名 | 候选 | 状态 | 质量分 |', '|---|---|---|---|---|']
    for r in rows:
        cells = [candidate_label(mapping[r['id']]) + '（编号 ' + r['id'] + '）', str(r['rank'] or '—'), identifier(mapping[r['id']]['id']), r['status'], '—' if r['total'] is None else f"{r['total']:.1f}"]
        lines.append('| ' + ' | '.join(cells) + ' |')
    lines += ['']
    for r in rows:
        item = mapping[r['id']]
        heading = f"{candidate_label(item)}（编号 {r['id']}）— 排名 {r['rank'] or '—'} — {r['status']} — {r['total'] if r['total'] is not None else '未评分'}"
        lines += ['## ' + heading, '']
        for key in ('summary', 'strengths', 'weaknesses', 'best_for', 'uncertainty'):
            lines += [f"**{key}**：{r[key]}", '']
        for key, d in r.get('dimensions', {}).items():
            text = f"{key}: {d['score']}/5 — {d['evidence']}"
            lines += ['- ' + text]
        for rel in item['artifacts']:
            p = safe_child(run / 'variants' / identifier(item['id']), rel)
            if not p.is_file():
                raise ValueError('Original artifact missing')
            lines += [f'- [{rel}](<{p.as_uri()}>)']
        lines += ['']
    first = candidate_label(mapping[rows[0]['id']])
    next_step = f'回到会话即可选择优化、重做、继续下一步或调整候选，并输入具体要求。也可直接说“优化 {first}：改进要求”或“先保留 {first}”。都不满意时，可增加两款新 skill，并选择移除指定候选或评分最低的两款；历史结果保留。'
    lines += ['## 接下来', '', next_step, '']
    (run / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    (run / 'report.html').write_text(render_reader(run, mapping, rows, title, safe_child, next_step), encoding='utf-8')
    write(run / 'ranking.json', {'results': rows})
    interaction(run, rows, mapping)
    return rows


def resolve_feedback(root, run_id, record):
    """Resolve an explicit request without writing or changing old results."""
    run = safe_child(Path(root) / 'runs', identifier(run_id))
    mode = record.get('mode')
    if mode not in {'select', 'refine', 'redo', 'continue', 'adjust'}:
        raise ValueError('Mode must be select, refine, redo, continue, or adjust')
    mapping = read(run / 'mapping.json')
    available = {identifier(item['id']): item for item in mapping.values()}
    variants = record.get('variants')
    adjustment = {}
    if mode == 'adjust':
        if variants is not None:
            raise ValueError('Adjust uses remove and add_count, not variants')
        add_count = record.get('add_count', 2)
        if type(add_count) is not int or add_count not in {0, 2}:
            raise ValueError('Add count must be 0 or 2')
        removed = record.get('remove', [])
        if removed == 'lowest-two':
            removed = lowest_two(run)
        if (not isinstance(removed, list) or any(not isinstance(v, str) for v in removed)
                or len(set(removed)) != len(removed) or any(v not in available for v in removed)):
            raise ValueError('Remove requires unique existing variant IDs')
        variants = [v for v in available if v not in removed]
        if (not removed and not add_count) or (not variants and not add_count):
            raise ValueError('Adjustment must change the roster and leave candidates')
        adjustment = {'removed_variants': removed, 'add_count': add_count}
    if variants is None and mode == 'continue':
        state = run / 'state.json'
        variants = read(state).get('selected') if state.exists() else None
    if variants == 'all' and mode == 'redo':
        variants = list(available)
    if (not isinstance(variants, list) or (not variants and mode != 'adjust')
            or any(not isinstance(v, str) for v in variants)
            or len(set(variants)) != len(variants)
            or any(v not in available for v in variants)):
        raise ValueError('Specify unique existing variant IDs; all is allowed only for redo')
    instruction = record.get('instruction', '')
    if not isinstance(instruction, str):
        raise ValueError('Instruction must be text')
    if mode in {'refine', 'continue'} and not instruction.strip():
        raise ValueError('Refine needs a requested change; continue needs the next task')
    user_message = record.get('user_message', instruction)
    if not isinstance(user_message, str):
        raise ValueError('User message must be text')
    parents = []
    for variant in variants:
        artifacts = []
        if mode in {'refine', 'continue'}:
            for rel in available[variant]['artifacts']:
                p = safe_child(run / 'variants' / variant, rel)
                if not p.is_file():
                    raise ValueError('Missing parent artifact: ' + str(p))
                artifacts.append({'path': p.relative_to(run).as_posix(),
                                  'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
            if not artifacts:
                raise ValueError('Selected branch has no artifacts')
        parents.append({'variant_id': variant, 'artifacts': artifacts})
    return {'run_id': run_id, 'mode': mode, 'variants': variants,
            'instruction': instruction.strip(), 'user_message': user_message, 'parents': parents,
            **adjustment}


def feedback(root, run_id, record):
    event = resolve_feedback(root, run_id, record)
    run = safe_child(Path(root) / 'runs', run_id)
    event.update(event_id=uuid.uuid4().hex, recorded_at=stamp())
    write(run / 'feedback' / (event['event_id'] + '.json'), event)
    state_path = run / 'state.json'
    state = read(state_path) if state_path.exists() else {'selected': []}
    state.update(last_event_id=event['event_id'], last_action=event['mode'])
    if event['mode'] in {'select', 'continue'}:
        state['selected'] = event['variants']
    write(state_path, state)
    return event


def followup(root, parent_id, child_id, record):
    request = resolve_feedback(root, parent_id, record)
    if request['mode'] == 'select':
        raise ValueError('Select only records a preference; use feedback, not followup')
    parent = safe_child(Path(root) / 'runs', parent_id)
    # Read required inputs before creating anything; invalid requests leave no child.
    original_task = (parent / 'task.md').read_text(encoding='utf-8')
    rubric = read(parent / 'rubric.json') if request['mode'] != 'continue' else None
    child = new_run(root, child_id)
    event = feedback(root, parent_id, record)
    write(child / 'lineage.json', {'parent_run_id': parent_id,
          'feedback_event_id': event['event_id'], 'mode': request['mode'],
          'variants': request['variants'], 'parents': request['parents'],
          'instruction': request['instruction'],
          'status': 'discovery-required' if request.get('add_count') else 'handoff-required',
          'removed_variants': request.get('removed_variants', []),
          'add_count': request.get('add_count', 0),
          'inherit_previous_answers': request['mode'] in {'refine', 'continue'}})
    task = request['instruction'] if request['mode'] == 'continue' else original_task
    if request['mode'] != 'continue' and request['instruction']:
        task += '\n\n## User follow-up\n\n' + request['instruction']
    (child / 'task.md').write_text(task + '\n', encoding='utf-8')
    if rubric is not None:
        write(child / 'rubric.json', rubric)
    (child / 'handoffs').mkdir()
    # A coordinator must still prepare each skill/context and freeze the new protocol.
    return child


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name, args in {'check-selection': ['record'], 'init': ['root'], 'register': ['root', 'record'], 'find': ['root', 'query'], 'new-run': ['root', 'id'], 'snapshot': ['run', 'id', 'source'], 'packet': ['run', 'manifest'], 'report': ['run'], 'remember': ['root', 'record'], 'feedback': ['root', 'run_id', 'record'], 'followup': ['root', 'parent_id', 'child_id', 'record']}.items():
        p = sub.add_parser(name)
        for arg in args:
            p.add_argument(arg)
    a = parser.parse_args()
    if a.command == 'check-selection': print(json.dumps(check_selection(a.record), ensure_ascii=False))
    elif a.command == 'init': init(a.root)
    elif a.command == 'register': register(a.root, read(a.record))
    elif a.command == 'new-run': print(new_run(a.root, a.id))
    elif a.command == 'snapshot': snapshot(a.run, a.id, a.source)
    elif a.command == 'packet': packet(a.run, read(a.manifest))
    elif a.command == 'report': report(a.run)
    elif a.command == 'feedback': print(json.dumps(feedback(a.root, a.run_id, read(a.record)), ensure_ascii=False))
    elif a.command == 'followup': print(followup(a.root, a.parent_id, a.child_id, read(a.record)))
    elif a.command == 'find':
        query = a.query.casefold().split()
        for s in read(Path(a.root) / 'registry.json')['skills']:
            text = json.dumps(s, ensure_ascii=False).casefold()
            if any(q in text for q in query): print(json.dumps(s, ensure_ascii=False))
        for line in (Path(a.root) / 'history.jsonl').read_text(encoding='utf-8').splitlines():
            if any(q in line.casefold() for q in query): print(line)
    elif a.command == 'remember':
        record = read(a.record)
        for key in ('run_id', 'task_tags', 'skill_versions', 'environment', 'status', 'report_path'):
            if key not in record: raise ValueError('History missing ' + key)
        if record.get('synthetic') is not False:
            raise ValueError('Set synthetic=false only for real trials; do not save test scores')
        record['recorded_at'] = stamp()
        with (Path(a.root) / 'history.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
