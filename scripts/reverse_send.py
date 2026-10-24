"""Run on remote host: stream one report through the loopback reverse tunnel."""
import argparse
import http.client
from pathlib import Path
import sys


def send(report, port, token):
    if not token or '\n' in token or '\r' in token: raise ValueError('Invalid token')
    report=Path(report)
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=60)
    try:
        conn.putrequest('POST','/report')
        conn.putheader('Authorization','Bearer '+token)
        conn.putheader('Content-Length',str(report.stat().st_size));conn.endheaders()
        with report.open('rb') as f:
            for block in iter(lambda:f.read(65536),b''):conn.send(block)
        response=conn.getresponse();body=response.read(65536).decode('utf-8')
        if response.status!=200: raise RuntimeError('Receiver rejected report: HTTP '+str(response.status))
        return body
    finally:conn.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('port',type=int)
    a=p.parse_args();print(send(a.report,a.port,sys.stdin.readline().strip()))
