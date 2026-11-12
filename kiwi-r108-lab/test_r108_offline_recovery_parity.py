#!/usr/bin/env python3
"""R108 synthetic archive comparator unit regressions, NOT Android recovery proof."""
import hashlib,importlib.util,json,tempfile,zipfile
from pathlib import Path
path=Path(__file__).with_name('r108_offline_recovery_parity.py')
spec=importlib.util.spec_from_file_location('r108_verify',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
base='http://127.0.0.1:18764'


def make(p,alter=None):
 req=[];rows=[];bins={}
 for seq in range(1,10):
  for j,(route,st) in enumerate((('/r104/api/alpha.json',200),('/r104/api/beta.txt',200),('/r104/api/expected-404',404),('/r104/api/tiny.svg',200))):
   x=len(req);url=f'{base}{route}?seq={seq}';rid=f'r{x}';body=(f'fixture:{seq}:{j}').encode()
   req.append({'requestEventId':f'req-{x}', 'nativeRequestId':rid,'url':url,'statusCode':st})
   name=f'Network/cdp_responses/response_{x}.bin'
   bins[name]=body
   rows.append({'key':rid,'captureSessionId':'old-session','requestId':rid,'url':url,'status':st,
                'bodyPath':name,'sha256':hashlib.sha256(body).hexdigest(),'capturedBytes':len(body)})
 if alter=='missing_request':req.pop()
 if alter=='new_request':req[0]['url']='http://other.invalid/forced'
 if alter=='wrong_body':
  b=bins[rows[0]['bodyPath']]+b'changed';bins[rows[0]['bodyPath']]=b
  rows[0]['sha256']=hashlib.sha256(b).hexdigest();rows[0]['capturedBytes']=len(b)
 if alter=='missing_binary':bins.pop(rows[-1]['bodyPath'])
 if alter=='duplicated_body':rows.append(dict(rows[0]))
 session='different-session' if alter=='new_session' else 'old-session'
 tr={'captureSessionId':session,'endedAt':'2026-11-12T00:01:00Z','active':False,'requests':req}
 with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('Trace/trace.json',json.dumps(tr))
  z.writestr('Network/cdp_response_index.json',json.dumps(rows))
  for n,b in bins.items():z.writestr(n,b)
  for k in range(20):z.writestr(f'Context/context_{k:03d}.json',json.dumps({'kind':'synthetic-padding','k':k}))
 return p

with tempfile.TemporaryDirectory() as t:
 root=Path(t);before=make(root/'before.zip');checks={}
 for key,expected in [('ok',True),('missing_request',False),('new_request',False),
                      ('wrong_body',False),('missing_binary',False),('duplicated_body',False),('new_session',False)]:
  after=make(root/f'{key}.zip',key if key!='ok' else None)
  result=mod.verify(before,after,root/f'{key}.json')
  passed=result['summary']['failed']==0
  assert passed==expected,(key,result)
  checks[key]={'expected':expected,'observed':passed,'failed_gates':[g for g,x in result['gates'].items() if x['status']=='FAIL']}
 print('R108_OFFLINE_COMPARATOR_REGRESSION',json.dumps(checks,ensure_ascii=False))
 Path('/mnt/data/r108_dev/r108_offline_regression.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
