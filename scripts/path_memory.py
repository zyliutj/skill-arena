"""Explicit, client-scoped preference block in a user-owned global memory file."""
import argparse
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

START='<!-- skill-arena:codex-temp-path:start -->'
END='<!-- skill-arena:codex-temp-path:end -->'


def read_memory(path):
    p=Path(path)
    raw=p.read_bytes().decode('utf-8-sig') if p.exists() else ''
    if raw.count(START)!=raw.count(END) or raw.count(START)>1:
        raise ValueError('Ambiguous memory block; preserve and review manually')
    if START not in raw: return raw, {'clients':{}}
    block=raw.split(START,1)[1].split(END,1)[0]
    m=re.search(r'```json\s*\n(.*?)\n```',block,re.S)
    if not m: raise ValueError('Invalid memory block; do not overwrite')
    return raw,json.loads(m[1])


def lookup(path, client):
    _,data=read_memory(path)
    return data['clients'].get(client)


def remember(path, client, local_root, fixed=False):
    if not fixed: raise ValueError('Requires explicit user consent to a fixed global path')
    if not client.strip() or not (PurePosixPath(local_root).is_absolute() or PureWindowsPath(local_root).is_absolute()):
        raise ValueError('Confirmed client and absolute local path required')
    path=Path(path)
    if path.is_symlink(): raise ValueError('Resolve the actual global memory file first')
    text,data=read_memory(path)
    data['clients'][client]={'codex_temp_root':local_root,'fixed':True}
    block=START+'\n## Codex 保存临时文件的路径\n\n以下路径由用户明确指定为固定的 Codex 本地临时文件保存路径；按客户端复用，不重复询问。Skill Arena 的本地报告也保存在此根目录的任务子目录；临时文件单独放 tmp，不自动删除报告。\n\n```json\n'+json.dumps(data,ensure_ascii=False,indent=2)+'\n```\n'+END
    if START in text:
        a=text.index(START); b=text.index(END,a)+len(END)
        updated=text[:a]+block+text[b:]
    else: updated=text+('\n\n' if text else '')+block+'\n'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(updated.encode('utf-8'))
    return lookup(path,client)


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('action',choices=['lookup','remember'])
    p.add_argument('memory');p.add_argument('client');p.add_argument('--path');p.add_argument('--fixed',action='store_true')
    a=p.parse_args()
    if a.action=='remember':
        if not a.path: p.error('--path required')
        result=remember(a.memory,a.client,a.path,a.fixed)
    else: result=lookup(a.memory,a.client)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
