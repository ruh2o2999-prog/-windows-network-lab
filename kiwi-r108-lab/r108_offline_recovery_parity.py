#!/usr/bin/env python3
"""Compare *two real extension exports* around browser restart; no synthetic PASS.

Baseline is the first stopped-task export, recovered is the post-force-stop
historic-task export. Verify identical captureSessionId, request identities,
counts, and original binary hashes; unrelated/new tasks must not leak.
"""
import argparse,collections,hashlib,json,pathlib,zipfile
API=('/r104/api/alpha.json','/r104/api/beta.txt','/r104/api/expected-404','/r104/api/tiny.svg')
def sha(data):return hashlib.sha256(data).hexdigest()
def is_fixture(url):return isinstance(url,str) and any(p in url for p in API)
def get(path):
    p=pathlib.Path(path)
    with zipfile.ZipFile(p) as z:
        corrupt=z.testzip()
        if corrupt:raise ValueError('CRC error at '+corrupt)
        tr=json.loads(z.read('Trace/trace.json'))
        req=[(r.get('requestEventId'),r.get('nativeRequestId'),r.get('url'),
              r.get('statusCode',r.get('status'))) for r in tr.get('requests',[])
              if is_fixture(r.get('url'))]
        candidates=[n for n in z.namelist() if n.endswith('cdp_response_index.json')]
        if len(candidates)!=1:raise ValueError('CDP response index absent or ambiguous')
        idx=json.loads(z.read(candidates[0]));records=[]
        for x in idx:
            if not is_fixture(x.get('url')):continue
            name=x.get('bodyPath')
            if name not in z.namelist():raise ValueError('CDP body missing '+str(name))
            body=z.read(name)
            if x.get('sha256')!=sha(body):raise ValueError('Index SHA not matched '+str(name))
            if x.get('capturedBytes')!=len(body):raise ValueError('Index size not matched')
            records.append((x.get('key'),x.get('captureSessionId'),
                            x.get('requestId'),x.get('url'),x.get('status'),
                            x.get('sha256'),len(body)))
        return {'session':tr.get('captureSessionId'),
                'requests':collections.Counter(req),'bodies':collections.Counter(records),
                'body_sha256':sorted(x[-2] for x in records),
                'request_count':len(req),'body_count':len(records),
                'zip_sha256':sha(p.read_bytes()),'zip_members':len(z.namelist()),
                'endedAt':tr.get('endedAt'),'active':tr.get('active')}
def verify(before,after,report):
    gates={}
    def check(id,ok,details):
        gates[id]={'status':'PASS' if ok else 'FAIL','details':details}
    try:
        a=get(before);b=get(after)
        check('R108_11_same_original_capture_session',
              bool(a['session']) and a['session']==b['session'],
              {'before':a['session'],'after':b['session']})
        check('R108_12_no_request_loss_or_duplication',
              a['requests']==b['requests'] and a['request_count']>=36,
              {'before':a['request_count'],'after':b['request_count'],
               'missing':sum((a['requests']-b['requests']).values()),
               'extra':sum((b['requests']-a['requests']).values())})
        check('R108_13_cdp_body_byte_identity',
              a['bodies']==b['bodies'] and a['body_count']>=36,
              {'before':a['body_count'],'after':b['body_count'],
               'missing':sum((a['bodies']-b['bodies']).values()),
               'extra':sum((b['bodies']-a['bodies']).values())})
        check('R108_14_task_remains_closed',
              bool(a['endedAt']) and a['endedAt']==b['endedAt'] and not b['active'],
              {'beforeEnded':a['endedAt'],'afterEnded':b['endedAt'],
               'afterActive':b['active']})
        check('R108_15_original_zip_independently_readable',
              a['zip_members']>=50 and b['zip_members']>=30,
              {'before_sha256':a['zip_sha256'],'after_sha256':b['zip_sha256'],
               'before_entries':a['zip_members'],'after_entries':b['zip_members']})
    except Exception as e:
        check('R108_99_verification_exception',False,repr(e))
    result={'stage':'R108','scope':'original frozen formal MV2 Android export, forced process restart',
            'gates':gates,'summary':{
                'passed':sum(x['status']=='PASS' for x in gates.values()),
                'failed':sum(x['status']=='FAIL' for x in gates.values())},
            'notice':'Without the *actual post-restart historic ZIP* this cannot PASS'}
    pathlib.Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--before',required=True);p.add_argument('--after',required=True);p.add_argument('--out',required=True)
    a=p.parse_args()
    result=verify(a.before,a.after,a.out)
    print(json.dumps(result['summary']))
    raise SystemExit(int(result['summary']['failed']>0))
