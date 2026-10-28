"""Offline, escaped HTML reader for Arena artifacts (no external scripts)."""
import base64
import csv
import html
import io
import json
import re
from pathlib import Path

E = html.escape

def inline(text):
    pattern = r'(`[^`]+`|\[[^\]]+\]\([^\s]+\)|\*\*[^*]+\*\*)'
    out = []
    for part in re.split(pattern, text):
        if part.startswith('`') and part.endswith('`'):
            out.append('<code>' + E(part[1:-1]) + '</code>')
        elif part.startswith('**') and part.endswith('**'):
            out.append('<strong>' + E(part[2:-2]) + '</strong>')
        else:
            m = re.fullmatch(r'\[([^\]]+)\]\(([^\s]+)\)', part)
            if m and m[2].startswith(('https://', 'http://', '#')):
                out.append('<a rel="noreferrer" href="' + E(m[2], quote=True) + '">' + E(m[1]) + '</a>')
            else:
                out.append(E(part))
    return ''.join(out)

def markdown(text):
    """Conservative Markdown subset; unsupported syntax remains readable text."""
    lines = text.splitlines(); result = []; i = 0; chapter = False
    while i < len(lines):
        line = lines[i]
        if line.startswith('```'):
            code = []; i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code.append(lines[i]); i += 1
            result.append('<pre><code>' + E('\n'.join(code)) + '</code></pre>'); i += 1; continue
        heading = re.match(r'^(#{1,6})\s+(.+)', line)
        if heading:
            level = len(heading[1])
            if level == 2:
                if chapter: result.append('</div></details>')
                result.append('<details class="chapter" open><summary>' + inline(heading[2]) + '</summary><div>'); chapter = True
            else:
                level = max(3, level)
                result.append(f'<h{level}>' + inline(heading[2]) + f'</h{level}>')
            i += 1; continue
        if i + 1 < len(lines) and '|' in line and re.fullmatch(r'[\s|:\-]+', lines[i+1]) and '-' in lines[i+1]:
            cells = lambda s: s.strip().strip('|').split('|')
            result.append('<div class="table-wrap"><table><thead><tr>' + ''.join('<th>'+inline(c.strip())+'</th>' for c in cells(line)) + '</tr></thead><tbody>'); i += 2
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                result.append('<tr>' + ''.join('<td>'+inline(c.strip())+'</td>' for c in cells(lines[i])) + '</tr>'); i += 1
            result.append('</tbody></table></div>'); continue
        item = re.match(r'^\s*(?:[-*+] |\d+[.)] )(.+)', line)
        if item:
            ordered = bool(re.match(r'^\s*\d+[.)] ', line)); tag = 'ol' if ordered else 'ul'
            result.append('<'+tag+'>')
            while i < len(lines):
                m = re.match(r'^\s*(?:\d+[.)] |[-*+] )(.+)', lines[i])
                if not m: break
                result.append('<li>'+inline(m[1])+'</li>'); i += 1
            result.append('</'+tag+'>'); continue
        if line.strip(): result.append('<p>'+inline(line)+'</p>')
        i += 1
    if chapter: result.append('</div></details>')
    return ''.join(result)

def artifact(path):
    ext = path.suffix.lower()
    if ext in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
        mime = 'image/' + ('jpeg' if ext in {'.jpg','.jpeg'} else ext[1:])
        return '<img alt="'+E(path.name)+'" src="data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()+'">'
    if ext in {'.md', '.txt', '.json', '.csv', '.py'}:
        text = path.read_text(encoding='utf-8-sig')
        if ext == '.md': return markdown(text)
        if ext == '.csv':
            rows = csv.reader(io.StringIO(text))
            return '<div class="table-wrap"><table>'+''.join('<tr>'+''.join('<td>'+E(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</table></div>'
        return '<pre>'+E(text)+'</pre>'
    # Binary formats remain embedded downloads; no active HTML/SVG is executed.
    return '<a download="'+E(path.name, quote=True)+'" href="data:application/octet-stream;base64,'+base64.b64encode(path.read_bytes()).decode()+'">下载 '+E(path.name)+'</a>'

CSS = '''body{margin:0;background:#f2f5fa;color:#1f2e46;font:16px/1.8 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1100px;margin:auto;padding:32px 24px 80px}header{background:#122842;color:white;padding:36px;border-radius:20px}header p{color:#d1e1ef}.eyebrow{letter-spacing:.16em;font-size:12px;color:#73dccb}h1{font-size:34px;margin:8px 0}h2{font-size:23px}h3{overflow-wrap:anywhere}nav{position:sticky;top:0;background:#f2f5faf5;z-index:2;padding:14px 0;display:flex;gap:8px;flex-wrap:wrap}button,nav a{background:white;border:1px solid #c9d6e5;border-radius:9px;padding:8px 12px;color:#183858;font:inherit;cursor:pointer;text-decoration:none}button:hover,nav a:hover{background:#e1f3f0}.panel{background:white;border:1px solid #dce4ef;border-radius:16px;padding:26px;margin:24px 0;scroll-margin-top:120px}.meta{background:#f4f7fb;border-radius:12px;padding:12px 22px}.meta li{margin:5px 0}details{margin:12px 0;border:1px solid #e1e7ef;border-radius:10px}summary{cursor:pointer;font-weight:650;padding:12px 16px;background:#f7f9fc;border-radius:10px}details>div{padding:8px 18px 18px}.chapter{border-left:3px solid #39a999}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;margin:14px 0;font-size:14px}th,td{border:1px solid #dce4ed;padding:10px;text-align:left;vertical-align:top}th{background:#edf3f9}p,li,td{overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f8;padding:16px;border-radius:8px;font-size:13px}code{background:#edf2f7;padding:1px 4px}a{color:#116f9b}img{max-width:100%;height:auto}.flow{display:flex;flex-wrap:wrap;align-items:center;gap:9px;list-style:none;padding:0}.flow li{background:#e7f6f2;border:1px solid #bdded5;padding:10px 16px;border-radius:9px}.flow li:not(:last-child):after{content:" →";color:#33816e}.muted{color:#62718a;font-size:14px}@media(max-width:600px){main{padding:16px 10px}header,.panel{padding:20px}h1{font-size:27px}nav{position:static}}@media print{nav{display:none}body{background:white}.panel{break-before:page}}'''
JS = '''document.querySelectorAll('[data-toggle]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('details').forEach(d=>d.open=b.dataset.toggle==='open')}));document.querySelectorAll('nav a').forEach(a=>a.addEventListener('click',()=>{const t=document.querySelector(a.getAttribute('href'));if(t){t.querySelectorAll('details').forEach(d=>{if(d.classList.contains('body'))d.open=true})}}));'''

def render(run, mapping, rows, title, safe_child, next_step, delivery=None):
    read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
    meta = {x['id']: x for x in read(run/'discovery.json').get('candidates', [])} if (run/'discovery.json').exists() else {}
    presentation = read(run/'presentation.json') if (run/'presentation.json').exists() else {}
    nav = []; sections = []; labels = {}
    mapping = dict(sorted(mapping.items(), key=lambda pair: pair[1].get('scheme_number', list(mapping).index(pair[0]) + 1)))
    for item in mapping.values():
        ident = item['id']; name = item.get('display_name') or item.get('skill_id') or ident
        baseline = item.get('kind') == 'baseline' or ident == 'baseline'
        if item.get('kind') == 'mixed-baseline': name = '多 skill 协作基线'
        if baseline: name = '普通提示词（无 skill）'
        name = '方案' + str(item.get('scheme_number', len(labels) + 1)) + ' · ' + str(name)
        labels[ident] = name
        data = {**meta.get(item.get('skill_id') or ident, {}), **item}
        view = presentation.get('candidates', {}).get(ident, {})
        data.update(view.get('metadata', {}))
        nav.append('<a href="#candidate-'+E(ident)+'">'+E(name)+'</a>')
        source = str(data.get('source',''))
        source_html = '<a href="'+E(source,quote=True)+'">'+E(data.get('repository') or source)+'</a>' if source.startswith(('https://','http://')) else '不适用' if baseline else '未记录'
        stars = str(data.get('stars')) if data.get('stars_status') == 'known' else '不适用' if baseline or data.get('stars_status')=='not_applicable' else '未获取'
        if data.get('stars_display'): stars = str(data['stars_display'])
        if item.get('kind') == 'mixed-baseline':
            source_html = '多个 skill 成员（详见运行记录）'
            stars = '不适用（成员分别核验，不合计）'
            data.setdefault('description', '优先按子任务优势组合多个 skill，独立整合完整方案。')
            data.setdefault('project_updated_at', '成员分别记录')
        checked = data.get('metadata_checked_at') or data.get('stars_checked_at')
        info = [('项目来源',source_html),('stars',E(stars)),('项目简介',E(str(data.get('description') or ('不加载候选 skill，以普通提示词完成相同任务。' if baseline else '未记录')))),('项目最新更新时间',E(str(data.get('project_updated_at') or ('不适用' if baseline else '未获取'))))]
        card = '<section class="panel" id="candidate-'+E(ident)+'"><h2>'+E(name)+'</h2><ul class="meta">'+''.join('<li><strong>'+k+'：</strong>'+v+'</li>' for k,v in info)+'</ul>'
        if checked: card += '<p class="muted">项目信息查询日期：'+E(str(checked))+'；项目更新时间采用最近代码推送时间（pushed_at），不是本轮快照日期。</p>'
        for diagram in view.get('diagrams', []):
            card += '<details><summary>'+E(diagram['title'])+' · 阅读示意</summary><div><ol class="flow">'+''.join('<li>'+E(x)+'</li>' for x in diagram['steps'])+'</ol><p class="muted">协调者根据原稿整理，不替代原文。依据：'+E(diagram['source'])+'</p></div></details>'
        for n, rel in enumerate(item['artifacts']):
            path = safe_child(run/'variants'/ident, rel)
            body = rel == 'answer.md' or n == 0
            label = '完整方案' if body else '参考资料' if rel == 'sources.md' else rel
            entry = next((x for x in (delivery or {}).get('artifacts', []) if x['path'] == 'variants/'+ident+'/'+rel), None)
            if entry and not entry['included']:
                content = artifact(path) if path.suffix.lower() in {'.md', '.txt'} else ''
                content += '<p>原始文件按需下载 · '+str(entry['bytes'])+' 字节 · 尚未同步</p><p>远程位置：'+E(delivery['source_host']+' : '+entry['source_path'])+'</p>'
            elif delivery:
                content = artifact(path) if path.suffix.lower() in {'.md','.txt','.json','.csv','.py','.png','.jpg','.jpeg','.gif','.webp'} else '<p>附件随交付包提供。</p>'
                content += '<p><a download href="'+E('variants/'+ident+'/'+rel,quote=True)+'">下载原始文件</a> · 随包传输，完成状态见 delivery-receipt.json</p>'
            else:
                content = artifact(path)+'<p><a download="'+E(path.name,quote=True)+'" href="data:application/octet-stream;base64,'+base64.b64encode(path.read_bytes()).decode()+'">下载原始文件</a></p>'
            card += '<details class="'+('body' if body else 'attachment')+'"'+(' open' if body else '')+'><summary>'+E(label)+'</summary><div>'+content+'</div></details>'
        sections.append(card+'</section>')
    assessment = '<section class="panel" id="evaluation"><h2>评估与比较</h2><p class="muted">分数仅适用于本次结果，接近时可并列；不代表技能的稳定优劣。</p><div class="table-wrap"><table><tr><th>候选</th><th>排名</th><th>状态</th><th>质量分</th><th>主要判断</th></tr>'
    for r in rows:
        item = mapping[r['id']]; name = labels[item['id']]
        assessment += '<tr><td>'+E(name)+'</td><td>'+str(r['rank'] or '—')+'</td><td>'+E(r['status'])+'</td><td>'+('—' if r['total'] is None else f'{r["total"]:.1f}')+'</td><td>'+E(r['summary'])+'</td></tr>'
    assessment += '</table></div>'
    for r in rows:
        name = labels[mapping[r['id']]['id']]
        assessment += '<details><summary>'+E(name)+' · 评分依据</summary><div><ul>'
        for key,label in [('strengths','优点'),('weaknesses','不足'),('best_for','适用场景'),('uncertainty','不确定性')]: assessment += '<li><b>'+label+'：</b>'+E(r[key])+'</li>'
        assessment += '</ul>'
        for key,d in r.get('dimensions',{}).items(): assessment += '<p><b>'+E(key)+' · '+str(d['score'])+'/5</b> '+E(d['evidence'])+'</p>'
        assessment += '</div></details>'
    for filename in ['verification.md','order-check.md']:
        p=run/'evaluation'/filename
        if p.exists(): assessment += '<details><summary>'+('事实核验记录' if filename=='verification.md' else '顺序复核记录')+'</summary><div>'+artifact(p)+'</div></details>'
    assessment += '</section>'
    records = '<details class="panel"><summary>运行记录与原始指令</summary><div>'
    for filename in ['protocol.json','discovery.md','discovery.json']:
        p=run/filename
        if p.exists(): records += '<details><summary>'+filename+'</summary><div>'+artifact(p)+'</div></details>'
    for item in mapping.values():
        for p in [run/'variants'/item['id']/'execution.json',run/'snapshots'/(item.get('skill_id') or item['id'])/'SKILL.md']:
            if p.exists(): records += '<details><summary>'+E(item['id']+' / '+p.name)+'</summary><div>'+artifact(p)+'</div></details>'
    records += '</div></details>'
    if delivery: records = '<p class="muted">最终报告优先交付；其他原始文件及运行记录保留在执行主机，需要时可按各方案列出的位置下载。传输完成情况以本地回执为准。</p>'
    brief = presentation.get('task_summary','本页收录各候选的完整产物。先阅读方案，再查看末尾评估。')
    task = '<details><summary>查看完整任务要求</summary><div>'+artifact(run/'task.md')+'</div></details>'
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+E(title)+'</title><style>'+CSS+'</style></head><body><main><header><span class="eyebrow">SKILL ARENA / READER</span><h1>'+E(title)+'</h1><p>'+E(brief)+'</p></header><nav><button data-toggle="open">全部展开</button><button data-toggle="close">全部收起</button>'+''.join(nav)+'<a href="#evaluation">查看评估</a></nav>'+task+''.join(sections)+assessment+'<p>'+E(next_step)+'</p>'+records+'</main><script>'+JS+'</script></body></html>'
