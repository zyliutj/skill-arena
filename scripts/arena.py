"""Local storage and report helpers. Standard library only; never calls a model."""
import argparse
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
    db = read(Path(root) / 'registry.json')
    record['checked_at'] = stamp()
    db['skills'] = [s for s in db['skills'] if s['id'] != record['id']] + [record]
    write(Path(root) / 'registry.json', db)


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
    lines = ['# ' + title, '', '方案编号固定，排名不作为选择编号。评分只适用于本次任务与版本；并列阈值不是统计置信区间。', '']
    lines += ['| 方案 | 排名 | 候选 | 状态 | 质量分 |', '|---|---|---|---|---|']
    table = '<table><tr><th>方案</th><th>排名</th><th>候选</th><th>状态</th><th>质量分</th></tr>'
    for r in rows:
        cells = [r['id'], str(r['rank'] or '—'), identifier(mapping[r['id']]['id']), r['status'], '—' if r['total'] is None else f"{r['total']:.1f}"]
        lines.append('| ' + ' | '.join(cells) + ' |')
        table += '<tr>' + ''.join('<td>' + html.escape(c) + '</td>' for c in cells) + '</tr>'
    lines += ['']
    cards = [table + '</table>']
    for r in rows:
        item = mapping[r['id']]
        heading = f"方案 {r['id']} · {item['id']} — 排名 {r['rank'] or '—'} — {r['status']} — {r['total'] if r['total'] is not None else '未评分'}"
        lines += ['## ' + heading, '']
        card = '<section><h2>' + html.escape(heading) + '</h2>'
        for key in ('summary', 'strengths', 'weaknesses', 'best_for', 'uncertainty'):
            lines += [f"**{key}**：{r[key]}", '']
            card += '<p><b>' + key + '</b>: ' + html.escape(r[key]) + '</p>'
        for key, d in r.get('dimensions', {}).items():
            text = f"{key}: {d['score']}/5 — {d['evidence']}"
            lines += ['- ' + text]
            card += '<p>' + html.escape(text) + '</p>'
        for rel in item['artifacts']:
            p = safe_child(run / 'variants' / identifier(item['id']), rel)
            if not p.is_file():
                raise ValueError('Original artifact missing')
            lines += [f'- [{rel}](<{p.as_uri()}>)']
            card += '<p><a href="' + html.escape(p.as_uri(), quote=True) + '">' + html.escape(rel) + '</a></p>'
        lines += ['']
        cards.append(card + '</section>')
    first = rows[0]['id']
    next_step = f'有满意的方案吗？可多选。回复“优化 {first}：改进要求”“重做 {first} / 全部重做”，或“满意 {first}，接着做：下一项任务”。也可以说“先保留 {first}”。'
    lines += ['## 接下来', '', next_step, '']
    cards.append('<section><h2>接下来</h2><p>' + html.escape(next_step) + '</p></section>')
    (run / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    (run / 'report.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Skill 对比报告</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:32px auto;padding:0 20px;background:#f5f7fa;color:#182539}section{background:white;border:1px solid #dde3ed;border-radius:12px;padding:24px;margin:20px 0}h1,h2{line-height:1.4}a{color:#1258af}p{white-space:pre-wrap}</style><h1>Skill 对比报告</h1><p>仅代表本次任务与版本；并列不是统计显著性结论。</p>' + ''.join(cards) + '</html>', encoding='utf-8')
    write(run / 'ranking.json', {'results': rows})
    if single:
        page = (run / 'report.html').read_text(encoding='utf-8').replace('Skill 对比报告', title)
        (run / 'report.html').write_text(page, encoding='utf-8')
    return rows


def resolve_feedback(root, run_id, record):
    """Resolve an explicit request without writing or changing old results."""
    run = safe_child(Path(root) / 'runs', identifier(run_id))
    mode = record.get('mode')
    if mode not in {'select', 'refine', 'redo', 'continue'}:
        raise ValueError('Mode must be select, refine, redo, or continue')
    mapping = read(run / 'mapping.json')
    available = {identifier(item['id']): item for item in mapping.values()}
    variants = record.get('variants')
    if variants is None and mode == 'continue':
        state = run / 'state.json'
        variants = read(state).get('selected') if state.exists() else None
    if variants == 'all' and mode == 'redo':
        variants = list(available)
    if (not isinstance(variants, list) or not variants
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
            'instruction': instruction.strip(), 'user_message': user_message, 'parents': parents}


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
          'instruction': request['instruction'], 'status': 'handoff-required',
          'inherit_previous_answers': request['mode'] != 'redo'})
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
    for name, args in {'init': ['root'], 'register': ['root', 'record'], 'find': ['root', 'query'], 'new-run': ['root', 'id'], 'snapshot': ['run', 'id', 'source'], 'packet': ['run', 'manifest'], 'report': ['run'], 'remember': ['root', 'record'], 'feedback': ['root', 'run_id', 'record'], 'followup': ['root', 'parent_id', 'child_id', 'record']}.items():
        p = sub.add_parser(name)
        for arg in args:
            p.add_argument(arg)
    a = parser.parse_args()
    if a.command == 'init': init(a.root)
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
