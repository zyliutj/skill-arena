"""Report-first delivery for local, mounted, or SSH-accessible workspaces."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath, PurePosixPath
import re
import shutil
import socket
import subprocess
import tempfile
from report_view import render

TEXT = {'.md', '.txt'}
LIMIT = 2 * 1024 * 1024
POSIX_CLIENT = os.name != "nt"


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    if path.is_symlink(): raise ValueError('Refusing symlink metadata target')
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def child(root, rel):
    if Path(rel).is_absolute() or PureWindowsPath(rel).is_absolute() or '..' in Path(rel).parts:
        raise ValueError('Unsafe relative path: ' + rel)
    root = Path(root).resolve()
    target = (root / rel).resolve()
    if not target.is_relative_to(root):
        raise ValueError('Path escapes root')
    return target


def detect(context='auto', environ=None):
    env = os.environ if environ is None else environ
    evidence = [key for key in ('SSH_CONNECTION', 'SSH_CLIENT', 'SSH_TTY') if env.get(key)]
    location = context if context != 'auto' else 'remote' if evidence else 'unknown'
    return {'location': location, 'host': socket.gethostname(), 'evidence': evidence,
            'note': 'No SSH variables does not prove local execution; use host context.'}


def destination(path):
    if os.name != 'nt' and PureWindowsPath(path).drive:
        raise ValueError('A Windows client path is not a mounted path on this host')
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ValueError('Destination must be an absolute, verified client or mount path')
    return p.resolve()


def export(run, output, full=False):
    """Build a new immutable delivery bundle; never copy caches or snapshots."""
    if os.name != 'nt' and PureWindowsPath(str(output)).drive:
        raise ValueError('Windows client output requires a verified mount on this host')
    run = Path(run).resolve(); output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Use a new delivery revision directory')
    if output == run or run.is_relative_to(output):
        raise ValueError('Output cannot contain the source run')
    mapping = read(run / 'mapping.json'); ranking = read(run / 'ranking.json')
    artifacts = []
    for item in mapping.values():
        for rel in item['artifacts']:
            p = child(run, 'variants/' + item['id'] + '/' + rel)
            size = p.stat().st_size
            # Narrative remains complete even when long; large data is optional.
            include = full or p.suffix.lower() in TEXT or size <= LIMIT
            artifacts.append({'path': 'variants/' + item['id'] + '/' + rel.replace('\\','/'), 'bytes': size,
                              'sha256': digest(p), 'included': include,
                              'source_path': str(p), 'status': 'bundled' if include else 'remote-only'})
    output.mkdir(parents=True)
    for item in artifacts:
        if item['included']:
            dest = child(output, item['path']); dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(child(run, item['path']), dest)
    manifest = {'schema': 1, 'source_host': socket.gethostname(), 'source_run': str(run),
                'mode': 'full' if full else 'report-first', 'artifacts': artifacts}
    title = '方案质量检查' if len(mapping) == 1 else 'Skill 对比报告'
    page = render(run, mapping, ranking['results'], title, child,
                  '回到会话选择优化、重做、接续或调整候选。', delivery=manifest)
    (output / 'report.html').write_text(page, encoding='utf-8')
    manifest['files'] = [{'path': 'report.html', 'bytes': (output/'report.html').stat().st_size,
                          'sha256': digest(output/'report.html')}]
    manifest['files'] += [{k: item[k] for k in ('path','bytes','sha256')}
                          for item in artifacts if item['included']]
    write(output/'delivery.json', manifest)
    return manifest


def sync(bundle, target):
    """Copy via an already accessible local/mounted path; verify and skip matches."""
    bundle = Path(bundle).resolve(); target = destination(str(target))
    if target == bundle or target.is_relative_to(bundle) or bundle.is_relative_to(target):
        raise ValueError('Delivery destination and bundle must be separate')
    manifest = read(bundle/'delivery.json'); copied = []; skipped = []
    # Verify the entire allowlist before writing any user files.
    for entry in manifest['files']:
        src = child(bundle, entry['path']); child(target, entry['path'])
        if digest(src) != entry['sha256']:
            raise ValueError('Source checksum mismatch: ' + entry['path'])
    target.mkdir(parents=True, exist_ok=True)
    for entry in manifest['files']:
        src = child(bundle, entry['path']); dst = child(target, entry['path'])
        if dst.is_file() and digest(dst) == entry['sha256']:
            skipped.append(entry['path']); continue
        if dst.exists():
            raise FileExistsError('Destination differs; use a new run/revision folder: ' + str(dst))
        dst.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dst.parent, delete=False, prefix='.arena-') as f:
            temp = Path(f.name)
        try:
            shutil.copyfile(src, temp)
            if digest(temp) != entry['sha256']: raise ValueError('Transfer checksum mismatch')
            os.replace(temp, dst)
        finally:
            temp.unlink(missing_ok=True)
        copied.append(entry['path'])
    write(target/'delivery.json', manifest)
    receipt = {'status':'verified', 'target':str(target), 'copied':copied, 'skipped':skipped,
               'files':manifest['files'], 'source_host':manifest['source_host']}
    write(target/'delivery-receipt.json', receipt)
    return receipt


def pull(host, remote_bundle, target):
    """Run on the LOCAL client; rsync over existing SSH config, never open a port."""
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', host):
        raise ValueError('Use an existing SSH host alias')
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', remote_bundle) or '..' in Path(remote_bundle).parts:
        raise ValueError('Use an absolute remote bundle path with ASCII letters/digits/_/./-/ only')
    target = destination(str(target))
    if not POSIX_CLIENT:
        raise RuntimeError('SSH pull requires a POSIX client; on Windows use a mounted directory or authorized file connector')
    if not shutil.which('rsync'):
        raise RuntimeError('rsync unavailable: use an authorized file connector or mounted directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Keep a resumable staging cache separate from the final destination.
    cache = target.parent / ('.' + target.name + '.arena-transfer')
    cache.mkdir(exist_ok=True)
    base = ['rsync', '--protect-args', '--checksum', '--partial', '-e',
            'ssh -o BatchMode=yes -o StrictHostKeyChecking=yes', '--']
    def fetch(rel):
        dst = child(cache, rel); dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(base + [host + ':' + remote_bundle.rstrip('/') + '/' + rel, str(dst)],
                       check=True, timeout=300)
    fetch('delivery.json')
    manifest = read(cache/'delivery.json')
    for entry in manifest['files']:
        rel=entry['path']; child(cache, rel)
        if not re.fullmatch(r'[A-Za-z0-9_./-]+', rel):
            raise ValueError('Unsupported remote artifact path; use mounted/connector transfer')
        existing=child(target,rel)
        if existing.is_file() and digest(existing)==entry['sha256']:
            staged=child(cache,rel); staged.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(existing,staged)
        else: fetch(rel)
        if rel == 'report.html':
            report = child(cache, rel)
            if digest(report) != entry['sha256']: raise ValueError('Report checksum mismatch')
            target.mkdir(parents=True, exist_ok=True)
            if existing.exists() and digest(existing) != entry['sha256']:
                raise FileExistsError('Destination report differs; use a new revision')
            if not existing.exists():
                with tempfile.NamedTemporaryFile(dir=target, delete=False, prefix='.arena-') as f:
                    pending = Path(f.name)
                try:
                    shutil.copyfile(report,pending); os.replace(pending,existing)
                finally: pending.unlink(missing_ok=True)
            write(target/'delivery-progress.json', {'status':'report-ready', 'pending':'attachments'})
    result = sync(cache, target)
    write(target/'delivery-progress.json', {'status':'verified', 'pending':[]})
    return result


def configure(root, client, local_root, mount=None):
    if not client.strip(): raise ValueError('Client identity is required')
    if not (PurePosixPath(local_root).is_absolute() or PureWindowsPath(local_root).is_absolute()):
        raise ValueError('Local root must be absolute')
    root=Path(root); root.mkdir(parents=True,exist_ok=True)
    path=root/'delivery-preferences.json'
    prefs=read(path) if path.exists() else {'clients':{}}
    prefs['clients'][client]={'local_root':local_root,'mount_on_remote':mount}
    write(path,prefs)
    return prefs


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    d=sub.add_parser('detect'); d.add_argument('--context',choices=['auto','local','remote'],default='auto')
    e=sub.add_parser('export'); e.add_argument('run'); e.add_argument('output'); e.add_argument('--full',action='store_true')
    s=sub.add_parser('sync'); s.add_argument('bundle'); s.add_argument('target')
    r=sub.add_parser('pull'); r.add_argument('host'); r.add_argument('remote_bundle'); r.add_argument('target')
    c=sub.add_parser('configure'); c.add_argument('root'); c.add_argument('client'); c.add_argument('local_root'); c.add_argument('--mount')
    a=p.parse_args()
    if a.cmd=='detect': result=detect(a.context)
    elif a.cmd=='export': result=export(a.run,a.output,a.full)
    elif a.cmd=='sync': result=sync(a.bundle,a.target)
    elif a.cmd=='configure': result=configure(a.root,a.client,a.local_root,a.mount)
    else: result=pull(a.host,a.remote_bundle,a.target)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

