"""One-report loopback receiver for an explicitly authorized SSH reverse tunnel."""
import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import socket
import tempfile
import time
from delivery import destination, verify_local


def accept_report(target, expected_hash, content):
    if hashlib.sha256(content).hexdigest()!=expected_hash:
        raise ValueError('Hash mismatch')
    report=target/'report.html'
    if report.is_symlink(): raise ValueError('Symlink target refused')
    if report.exists():
        if hashlib.sha256(report.read_bytes()).hexdigest()!=expected_hash:
            raise ValueError('Existing report differs; choose a new task revision')
    else:
        with tempfile.NamedTemporaryFile(dir=target,delete=False,prefix='.arena-') as f:
            temp=Path(f.name);f.write(content)
        try: os.replace(temp,report)
        finally: temp.unlink(missing_ok=True)
    return verify_local(target,expected_hash,socket.gethostname())


def serve(target, expected_hash, expected_bytes, token_file, port=0, timeout=600):
    target=destination(str(target))
    if not re.fullmatch('[0-9a-f]{64}',expected_hash) or not 0<expected_bytes<=64*1024*1024:
        raise ValueError('Require final source hash and report size in (0,64 MiB]')
    target.mkdir(parents=True,exist_ok=True)
    token_file=Path(token_file)
    token=secrets.token_urlsafe(32)
    # Exclusive creation, no secret in stdout or process arguments.
    fd=os.open(token_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f: f.write(token)
    complete=[False]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            self.connection.settimeout(30)
            if self.path!='/report' or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                self.send_error(403);return
            try:
                if self.headers.get('Transfer-Encoding') or int(self.headers.get('Content-Length','-1'))!=expected_bytes:
                    self.send_error(400);return
                payload=self.rfile.read(expected_bytes)
                proof=accept_report(target,expected_hash,payload)
                self.send_response(200);self.end_headers()
                self.wfile.write(json.dumps(proof).encode());complete[0]=True
            except (ValueError,OSError): self.send_error(400)
    try:
        with HTTPServer(('127.0.0.1',port),Handler) as server:
            server.timeout=1
            print(json.dumps({'listening':'127.0.0.1','port':server.server_port,'token_file':str(token_file)}),flush=True)
            deadline=time.monotonic()+timeout
            while not complete[0] and time.monotonic()<deadline: server.handle_request()
        if not complete[0]: raise TimeoutError('No verified report received before deadline')
    finally: token_file.unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('target');p.add_argument('sha256');p.add_argument('bytes',type=int);p.add_argument('token_file')
    p.add_argument('--port',type=int,default=0);p.add_argument('--timeout',type=int,default=600)
    a=p.parse_args();serve(a.target,a.sha256,a.bytes,a.token_file,a.port,a.timeout)

if __name__=='__main__': main()
