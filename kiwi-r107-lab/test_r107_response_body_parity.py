#!/usr/bin/env python3
"""R107 independent byte-parity positive/negative regression (public synthetic only)."""
import copy,hashlib,json,tempfile,zipfile
from pathlib import Path
from r107_response_body_parity import verify,ROUTES
def sh(b):return hashlib.sha256(b).hexdigest()
def fixture():
    bodies={}
    for path in ROUTES:
        if path.endswith("alpha.json"):body=b'{"fixture":"R104","route":"alpha","result":"known","status":200}'
        elif path.endswith("beta.txt"):body=b'R104_FIXTURE_BETA_RESPONSE_0123456789\n'
        elif path.endswith("expected-404"):body=b'R104_CONTROLLED_EXPECTED_404\n'
        elif path.endswith("tiny.svg"):body=b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><rect width="1" height="1"/></svg>'
        else:raise AssertionError(path)
        bodies[path]=body
    return bodies
def make():
    bodies=fixture();index=[];entries={};truth=[]
    for seq in range(1,10):
        for path,status in ROUTES.items():
            body=bodies[path];i=len(index)+1;rid=str(i)
            url='http://127.0.0.1:18764'+path+'?seq='+str(seq)
            member='Network/cdp_responses/response_'+str(i).zfill(5)+'.bin'
            entries[member]=body
            index.append({'key':'frozen|tab=2|root|'+rid,'captureSessionId':'test-session',
                'captureInstanceId':'a1','cdpSessionId':None,'requestId':rid,'redirectOrdinal':0,
                'tabId':2,'url':url,'status':status,'source':'cdp-network-getResponseBody',
                'sha256':sh(body),'capturedBytes':len(body),'bodyPath':member,
                'bodyStatus':'captured_complete','exportVerified':True,'rawWireBytes':False})
            truth.append({'url':path+'?seq='+str(seq),'status':status,'time_ns':2000,
                          'bytes':len(body),'body_sha256':sh(body)})
    return index,entries,truth
def run_case(root,name,mutator,expected):
    folder=root/name;folder.mkdir()
    index,entries,truth=make();mutator(index,entries,truth)
    with zipfile.ZipFile(folder/'source.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('Network/cdp_response_index.json',json.dumps(index))
        for path,body in entries.items():z.writestr(path,body)
    (folder/'truth.jsonl').write_text('\n'.join(json.dumps(x) for x in truth)+'\n')
    report=verify(folder/'source.zip',folder/'truth.jsonl',1000,3000,folder/'report.json',
                  folder/'controlled.zip',min_events=36)
    passed=report['summary']['failed']==0
    assert passed==expected,(name,report['gates'])
    assert (folder/'controlled.zip').exists()==expected,name
    return {'actual':'PASS' if passed else 'FAIL_AS_EXPECTED',
            'failed_gates':[k for k,v in report['gates'].items() if v['status']=='FAIL']}
def nothing(i,e,t):pass
def modified_body(i,e,t):e[i[4]['bodyPath']]=b'TAMPERED'
def wrong_server_hash(i,e,t):t[6]['body_sha256']='0'*64
def missing(i,e,t):e.pop(i[1]['bodyPath'])
def wrong_id(i,e,t):i[0]['requestId']=''
def collision(i,e,t):i[1]['requestId']=i[0]['requestId'];i[1]['key']=i[0]['key']
def wrong_404(i,e,t):
    row=next(r for r in i if 'expected-404' in r['url']);row['status']=200
def untrusted_source(i,e,t):i[0]['source']='page-hook'
def unavailable(i,e,t):i[0]['bodyStatus']='body_unavailable'
def missing_index(i,e,t):i.pop(3)
def duplicate_index(i,e,t):i.append(copy.deepcopy(i[0]))
def wrong_body_length(i,e,t):i[0]['capturedBytes']+=1
def add_unlogged(i,e,t):
    a=copy.deepcopy(i[0]);a['url']=a['url'].replace('seq=1','seq=10');a['requestId']='new'
    a['key']='new';i.append(a)
cases=[
    ('genuine_binary_bytes',nothing,True),
    ('tampered_bin_detected',modified_body,False),
    ('independent_server_sha_detected',wrong_server_hash,False),
    ('missing_bin_detected',missing,False),
    ('missing_browser_request_id',wrong_id,False),
    ('duplicate_browser_request_id',collision,False),
    ('wrong_404_status',wrong_404,False),
    ('page_hook_fake_source',untrusted_source,False),
    ('partial_body_declared',unavailable,False),
    ('missing_index_row',missing_index,False),
    ('duplicate_index_row',duplicate_index,False),
    ('incorrect_declared_length',wrong_body_length,False),
    ('unlogged_extra_body',add_unlogged,False),
]
with tempfile.TemporaryDirectory(prefix='r107_regression_') as directory:
    results={}
    for name,change,expected in cases:
        results[name]=run_case(Path(directory),name,change,expected)
print('R107_BYTE_PARITY_REGRESSIONS',json.dumps(results,sort_keys=True))
