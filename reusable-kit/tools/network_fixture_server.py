#!/usr/bin/env python3
"""PROBE controlled HTTP fixture: real request ground truth for browser or Android AVD.
No private plugin/source is served or copied. All data are public synthetic data.
"""
import argparse, json, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = """<!doctype html><html><head><meta charset="UTF-8"><title>PROBE browser Real Network Fixture</title></head>
<body><h1>PROBE_NETWORK_FIXTURE_READY</h1><p id="status">Starting controlled traffic</p>
<button id="run">RUN_PROBE_KNOWN_REQUESTS</button>
<script>
let seq = 0;
async function fire() {
  const n = ++seq; const paths = [
    '/probe/api/alpha.json?seq='+n,
    '/probe/api/beta.txt?seq='+n,
    '/probe/api/expected-404?seq='+n,
    '/probe/api/tiny.svg?seq='+n
  ];
  const results=await Promise.allSettled(paths.map(p=>fetch(p,{cache:'no-store'})));
  document.getElementById('status').textContent='PROBE_NETWORK_TICK_'+n+'_'+results.length;
}
document.getElementById('run').addEventListener('click',fire);
setTimeout(fire,1600);
setInterval(fire,3200);
</script></body></html>"""

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--port',type=int,default=18764)
    ap.add_argument('--log',required=True,type=Path)
    a=ap.parse_args()
    a.log.parent.mkdir(parents=True,exist_ok=True)
    lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path=urllib.parse.urlsplit(self.path).path
            status=200
            if path=='/':
                body=PAGE.encode(); mime='text/html; charset=utf-8'
            elif path=='/probe/api/alpha.json':
                body=json.dumps({'fixture':'PROBE','route':'alpha','result':'known','status':200}).encode()
                mime='application/json; charset=utf-8'
            elif path=='/probe/api/beta.txt':
                body=b'PROBE_FIXTURE_BETA_RESPONSE_0123456789\n';mime='text/plain'
            elif path=='/probe/api/expected-404':
                body=b'PROBE_CONTROLLED_EXPECTED_404\n';mime='text/plain';status=404
            elif path=='/probe/api/tiny.svg':
                body=b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><rect width="1" height="1"/></svg>'
                mime='image/svg+xml'
            elif path=='/favicon.ico':
                body=b'';mime='image/x-icon';status=204
            else:
                body=b'not found';mime='text/plain';status=404
            event={'time_ns':time.time_ns(),'method':'GET','url':self.path,'path':path,'status':status,'bytes':len(body)}
            with lock:
                with a.log.open('a',encoding='utf-8') as f:f.write(json.dumps(event,sort_keys=True)+'\n')
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            if body:self.wfile.write(body)
        def log_message(self,fmt,*args):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
    print('PROBE_FIXTURE_SERVER_READY',a.port,flush=True)
    try:server.serve_forever(poll_interval=0.2)
    finally:server.server_close()
if __name__=='__main__':main()
