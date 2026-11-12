#!/usr/bin/env python3
"""R106: regression for the frozen formal MV2 V0.4.58 KiwiTrace.view schema.
Synthetic records derived from actual trace-core.js; NOT an Android A7 PASS.
Original R104 tests and failures remain independently preserved.
"""
import copy
import json
import tempfile
import zipfile
from pathlib import Path
from r104_network_strict_parity import verify, ROUTES

BASE='http://127.0.0.1:18764'

def case(root,name,variant=None,expected=True):
    requests=[];har=[];trace_requests=[];timeline=[];host=[]
    for seq in (1,2):
        for route,status in ROUTES.items():
            url=f'{BASE}{route}?seq={seq}'
            rid=f'req-{len(requests)+1}'
            requests.append({'requestId':rid,'url':url,'method':'GET','statusCode':status})
            har.append({'request':{'url':url,'method':'GET'},'response':{'status':status}})
            trace_requests.append({'requestEventId':rid,'nativeRequestId':rid,
                                   'tabId':2,'url':url,'statusCode':status,'finished':True})
            timeline.extend([{'eventId':'start-'+rid,'type':'request-started','url':url},
                             {'eventId':'end-'+rid,'type':'request-completed',
                              'requestEventId':rid,'statusCode':status}])
            host.append({'url':route+f'?seq={seq}','status':status,'time_ns':1200})
    trace={'schemaVersion':1,'captureSessionId':'fixture-123','requests':trace_requests,
           'timeline':timeline,'counts':{'requests':8,'timeline':16}}
    if variant=='noise':trace['timeline'].extend(copy.deepcopy(timeline))
    if variant=='missing':trace['requests'].pop()
    if variant=='duplicate':trace['requests'].append(copy.deepcopy(trace['requests'][0]))
    if variant=='wrong_seq':trace['requests'][0]['url']=trace['requests'][0]['url'].replace('seq=1','seq=11')
    if variant=='unknown':trace.pop('requests')
    if variant=='ambiguous':trace['traceEvents']=copy.deepcopy(trace['requests'])
    folder=root/name;folder.mkdir()
    with zipfile.ZipFile(folder/'export.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('current/Network/requests.json',json.dumps(requests))
        z.writestr('current/Network/network.har',json.dumps({'log':{'entries':har}}))
        z.writestr('Trace/trace.json',json.dumps(trace))
    (folder/'server.jsonl').write_text('\n'.join(map(json.dumps,host))+'\n')
    verdict=verify(folder/'export.zip',folder/'server.jsonl',1000,2000,folder/'result.json')
    success=verdict['status']['failed']==0
    assert success==expected,(name,verdict['gates'])
    if not expected:
        assert verdict['gates']['STRICT_07_trace_exact']['status']=='FAIL',name
    return {'expected_pass':expected,'observed_pass':success,
            'trace_count':verdict['gates']['STRICT_07_trace_exact']['detail'].get('export_events')}

all_cases=[('formal_trace_timeline_duplication',None,True),
           ('timeline_noise_not_a_network_request','noise',True),
           ('missing_trace_request_detected','missing',False),
           ('duplicated_trace_request_detected','duplicate',False),
           ('wrong_trace_sequence_detected','wrong_seq',False),
           ('unknown_trace_schema_rejected','unknown',False),
           ('ambiguous_trace_schema_rejected','ambiguous',False)]
with tempfile.TemporaryDirectory(prefix='r106_trace_') as temporary:
    results={n:case(Path(temporary),n,v,p) for n,v,p in all_cases}
print('R106_FORMAL_TRACE_SCHEMA_REGRESSION',json.dumps(results,sort_keys=True))
