#!/usr/bin/env python3
"""R122 official Android Kiwi bounded soak. Read-only runtime sampling.
This experiment does not claim R121-13 24-hour completion or prove absence of leaks.
"""
import csv, json, re, statistics, time
from pathlib import Path
from r109_history_recovery import cdp_eval

PKG='com.kiwibrowser.browser'

def _mem(raw):
    patterns=(r'TOTAL PSS:\s*([\d,]+)',r'^\s*TOTAL\s+([\d,]+)\s',r'\*\* MEMINFO.*?TOTAL PSS:\s*([\d,]+)')
    for pat in patterns:
        m=re.search(pat,raw,re.M|re.S)
        if m:
            return int(m.group(1).replace(',',''))
    return None

def execute(run,ws,tab_id,fixture,out,state,seconds=240,interval=15):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    result={'name':'R122 real Kiwi resource soak','scope':'Android11 API30 Kiwi, localhost-only traffic','secondsRequested':seconds,'sampleInterval':interval,
            'gates':{},'samples':[],'errors':[],'notClaimed':['R121-13 24-hour soak','Android16 ARM64','zero memory leaks proven','all real websites']}
    js="(async()=>new Promise((ok,no)=>chrome.runtime.sendMessage({type:'R121_STATUS',tabId:"+str(tab_id)+"},r=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):ok(r))))()"
    initial_hits=fixture.hits
    begin=time.monotonic()
    target_n=max(12,int(seconds/interval)+1)
    for i in range(target_n):
        sleep_for=begin+i*interval-time.monotonic()
        if sleep_for>0:time.sleep(sleep_for)
        t=time.monotonic()
        s={'sample':i,'elapsedSec':round(t-begin,2),'fixtureHttpHits':fixture.hits,'unixTime':time.time()}
        rc,pids=run(['adb','shell','pidof',PKG],timeout=14)
        s['pidofRc']=rc;s['pids']=pids.strip()[:160]
        rc,mem=run(['adb','shell','dumpsys','meminfo',PKG],timeout=30)
        s['meminfoRc']=rc;s['pssKiB']=_mem(mem) if rc==0 else None
        if i in (0,3,6,9,target_n-1):(out/f'r122_meminfo_{i:02}.txt').write_text(mem[-25000:],encoding='utf8')
        try:
            v=cdp_eval(ws,js,timeout=18)
            c=(v or {}).get('capture') or {};p=(v or {}).get('passive') or {}
            s.update({'cdpOk':True,'mode':c.get('mode'), 'activeCount':c.get('activeCount'),
                'bodyBudgetBytes':(c.get('limits') or {}).get('maxCdpSessionBytes'),
                'storageUsage':((c.get('storage') or {}).get('usage')),
                'storagePressure':((c.get('storage') or {}).get('pressure')),
                'passiveFindings':len(p.get('findings') or []),'activeSecurityRequests':p.get('activeRequestsSent'),
                'captureError':c.get('lastError'),'degraded':c.get('degraded')})
        except Exception as e:
            s['cdpOk']=False;s['cdpError']=repr(e)
        result['samples'].append(s)
        print('R122_SOAK_SAMPLE',json.dumps({k:s.get(k) for k in ('sample','elapsedSec','fixtureHttpHits','pids','pssKiB','mode','activeCount','storageUsage','storagePressure','cdpOk','cdpError')},ensure_ascii=False),flush=True)
    elapsed=time.monotonic()-begin
    samples=result['samples'];valid=[x for x in samples if x.get('pssKiB') is not None]
    ok_modes=[x for x in samples if x.get('cdpOk') and x.get('mode')=='debugger']
    last3=[x['pssKiB'] for x in valid[-3:]];first3=[x['pssKiB'] for x in valid[:3]]
    result['summary']={'actualElapsedSec':round(elapsed,2),'httpDelta':fixture.hits-initial_hits,
        'sampleCount':len(samples),'pssValid':len(valid),'peakPssKiB':max((x['pssKiB'] for x in valid),default=None),
        'initialPssMedianKiB':statistics.median(first3) if first3 else None,
        'finalPssMedianKiB':statistics.median(last3) if last3 else None,
        'pssGrowthKiB':round(statistics.median(last3)-statistics.median(first3),1) if first3 and last3 else None,
        'errorCount':sum(not x.get('cdpOk') for x in samples),
        'pidSets':sorted(set(x.get('pids') or '' for x in samples))}
    def gate(k,ok,e):
        status='PASS' if ok else 'FAIL';result['gates'][k]={'status':status,'evidence':e}
        state['gates'][k]={'status':status,'detail':json.dumps(e,ensure_ascii=False)[:1700]}
        print('R122_'+status+' '+k+' '+json.dumps(e,ensure_ascii=False)[:450],flush=True)
    gate('R122-01_real_soak_samples',len(samples)>=12 and elapsed>=seconds*.90,{'samples':len(samples),'elapsed':round(elapsed,1)})
    gate('R122-02_auto_debugger_remained_connected',len(ok_modes)>=len(samples)-1,{'good':len(ok_modes),'samples':len(samples)})
    gate('R122-03_passive_security_no_active_probe',all(x.get('activeSecurityRequests')==0 and x.get('passiveFindings',0)>=2 for x in samples if x.get('cdpOk')),{'checked':sum(bool(x.get('cdpOk')) for x in samples)})
    gate('R122-04_real_page_traffic_continues',fixture.hits-initial_hits>=max(100,int(seconds*1.5)),{'requestsDelta':fixture.hits-initial_hits})
    gate('R122-05_storage_remains_under_soft_limit',all((x.get('storageUsage') or 0)<268435456 and x.get('storagePressure') is False for x in samples if x.get('cdpOk')),{'lastUsage':samples[-1].get('storageUsage')})
    gate('R122-06_android_memory_process_reproducible',len(valid)>=len(samples)-1 and all(x.get('pids') for x in samples),{'validMeminfoSamples':len(valid),'peakPssKiB':result['summary']['peakPssKiB'],'uniquePidSets':len(result['summary']['pidSets'])})
    result['gates']['R121-13_24h_soak']={'status':'NOT_RUN','evidence':'R122 sampled only '+str(round(elapsed))+' seconds; 24h baseline remains open'}
    with (out/'r122_android_soak.csv').open('w',newline='',encoding='utf8') as f:
        cols=sorted(set().union(*(x.keys() for x in samples)))
        writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader();writer.writerows(samples)
    (out/'r122_android_soak.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result
