#!/usr/bin/env python3
"""R123 local-repaired R122 Android Kiwi soak probe.

No broad claims: R121-13 24h and Android16 remain NOT_RUN until real evidence.
One status attempt per sample; an independent health probe after failures is
strictly diagnostic, never upgrades a failed sample to PASS.
"""
import csv
import json
import re
import statistics
import time
from pathlib import Path
from r109_history_recovery import cdp_eval
from r125_diagnostic_probe import annotate_sample, evaluate_diagnostic_gates

PKG = 'com.kiwibrowser.browser'
SOFT_LIMIT = 268435456


def _mem(raw):
    for pat in (r'TOTAL PSS:\s*([\d,]+)', r'^\s*TOTAL\s+([\d,]+)\s'):
        m = re.search(pat, raw, re.M)
        if m:
            return int(m.group(1).replace(',', ''))
    return None


def status_expression(tab_id, callback_timeout_ms=6000):
    """Browser extension status with its own deadline, distinct from CDP socket."""
    tab_id = int(tab_id)
    if tab_id <= 0:
        raise ValueError('expected positive tab ID')
    return '''(async()=>new Promise((resolve,reject)=>{
      const t=setTimeout(()=>reject(Error('R122_STATUS_CALLBACK_TIMEOUT')),''' + str(int(callback_timeout_ms)) + ''');
      try {chrome.runtime.sendMessage({type:'R121_STATUS',tabId:''' + str(tab_id) + '''},r=>{
        clearTimeout(t);
        const err=chrome.runtime.lastError;
        if(err){reject(Error('R122_RUNTIME_LAST_ERROR:'+err.message));return;}
        if(!r||typeof r!=='object'){
          reject(Error('R122_INVALID_STATUS_RESPONSE'));return;
        }
        resolve(r);
      });}catch(e){clearTimeout(t);reject(Error('R122_STATUS_DISPATCH:'+String(e)));}
    }))()'''


def classify_error(first_error, health_error=None, health=None):
    raw = repr(first_error)
    # A syntactically returned but empty/invalid probe does not prove CDP alive.
    healthy = isinstance(health, dict) and health.get('r122CdpAlive') is True
    if 'R122_STATUS_CALLBACK_TIMEOUT' in raw:
        return 'EXTENSION_STATUS_CALLBACK_TIMEOUT'
    if 'R122_RUNTIME_LAST_ERROR' in raw:
        return 'EXTENSION_RUNTIME_LAST_ERROR'
    if 'R122_INVALID_STATUS_RESPONSE' in raw:
        return 'INVALID_STATUS_RESPONSE'
    if any(x in raw for x in ('WebSocketTimeoutException', 'TimeoutError', 'Connection timed out')):
        if healthy:
            return 'STATUS_PATH_DELAY_WITH_CDP_ALIVE'
        if health_error is not None:
            return 'CDP_TRANSPORT_OR_TARGET_UNRESPONSIVE'
        return 'CDP_HEALTH_NOT_CONFIRMED'
    if healthy:
        return 'STATUS_RUNTIME_ERROR_CDP_ALIVE'
    return 'STATUS_OR_CDP_UNKNOWN'


def read_status(ws, tab_id, cdp=cdp_eval):
    """Always preserve first failure; a separate ping never counts as status data."""
    result = {'cdpOk': False, 'healthProbeAttempted': False}
    try:
        data = cdp(ws, status_expression(tab_id), timeout=11)
        if not isinstance(data, dict) or not isinstance(data.get('capture'), dict) or not isinstance(data.get('passive'), dict):
            raise ValueError('R122_INVALID_STATUS_RESPONSE')
        result.update({'cdpOk': True, 'status': data, 'errorClass': None})
    except Exception as e:
        result['cdpError'] = repr(e)
        result['healthProbeAttempted'] = True
        health = None
        health_error = None
        try:
            health = cdp(ws, '({r122CdpAlive:true,ready:document.readyState,ts:Date.now()})', timeout=4)
            result['cdpHealth'] = health
        except Exception as ex:
            health_error = ex
            result['cdpHealthError'] = repr(ex)
        result['errorClass'] = classify_error(e, health_error, health)
    return result


def status_fields(status):
    c = status['capture']
    p = status['passive']
    storage = c.get('storage')
    if not isinstance(storage, dict):
        storage = {}
    usage = storage.get('usage')
    pressure = storage.get('pressure')
    valid_storage = type(usage) is int and usage >= 0 and type(pressure) is bool
    return {
        'mode': c.get('mode'), 'activeCount': c.get('activeCount'),
        'storageUsage': usage, 'storagePressure': pressure,
        'storageValid': valid_storage,
        'passiveFindings': len(p.get('findings') or []),
        'activeSecurityRequests': p.get('activeRequestsSent'),
        'captureError': c.get('lastError'), 'degraded': c.get('degraded'),
        'bodyBudgetBytes': (c.get('limits') or {}).get('maxCdpSessionBytes'),
    }


def evaluate_gates(samples, http_delta, actual_elapsed, seconds):
    """Strict, non-vacuous grading. Missing observations always prevent PASS."""
    n = len(samples)
    complete = all(s.get('cdpOk') is True for s in samples) and n > 0
    # Never trust a cached storageValid flag in isolation: derive actual types.
    typed_storage = complete and all(
        s.get('storageValid') is True
        and type(s.get('storageUsage')) is int and s['storageUsage'] >= 0
        and type(s.get('storagePressure')) is bool for s in samples)
    pss_valid = n > 0 and all(type(s.get('pssKiB')) is int and s['pssKiB'] > 0 for s in samples)
    pid_valid = n > 0 and all(s.get('pids') and s.get('pidofRc') == 0 for s in samples)
    pids = [s.get('pids') for s in samples]
    result = {
        'R122-01_real_soak_samples': (n >= 12 and actual_elapsed >= seconds * .90, {'samples': n, 'elapsed': round(actual_elapsed, 1)}),
        'R122-02_auto_debugger_remained_connected': (complete and all(s.get('mode') == 'debugger' for s in samples), {'validStatus': sum(bool(s.get('cdpOk')) for s in samples), 'samples': n}),
        'R122-03_passive_security_no_active_probe': (complete and all(s.get('activeSecurityRequests') == 0 and s.get('passiveFindings', 0) >= 2 for s in samples), {'checked': sum(bool(s.get('cdpOk')) for s in samples)}),
        'R122-04_real_page_traffic_continues': (http_delta >= max(100, int(seconds * 1.5)), {'requestsDelta': http_delta}),
        'R122-05_storage_remains_under_soft_limit': (typed_storage and all(s['storagePressure'] is False and s['storageUsage'] < SOFT_LIMIT for s in samples), {'validStorage': sum(bool(s.get('storageValid')) for s in samples), 'samples': n}),
        'R122-06_android_memory_process_reproducible': (pss_valid and pid_valid and len(set(pids)) == 1, {'validMeminfo': sum(type(s.get('pssKiB')) is int for s in samples), 'pidSets': len(set(pids))}),
        'R122-07_all_cdp_reads_acknowledged': (complete, {'valid': sum(bool(s.get('cdpOk')) for s in samples), 'total': n, 'errors': [{'sample': s.get('sample'), 'class': s.get('errorClass')} for s in samples if not s.get('cdpOk')]}),
        'R122-08_all_storage_samples_observed': (typed_storage, {'validStorage': sum(bool(s.get('storageValid')) for s in samples), 'total': n}),
    }
    return {k: {'status': 'PASS' if ok else 'FAIL', 'evidence': evidence} for k, (ok, evidence) in result.items()}


def execute(run, ws, tab_id, fixture, out, state, seconds=300, interval=15, cdp=cdp_eval):
    """Run only within real Android Kiwi runner; no simulated PASS written here."""
    out = Path(out);out.mkdir(parents=True, exist_ok=True)
    report = {'name': 'R123 candidate / R122 native bounded soak', 'scope': 'official Kiwi Android 11, controlled localhost only - R125',
              'secondsRequested': seconds, 'sampleInterval': interval, 'samples': [], 'errors': [],
              'notClaimed': ['R121-13 24-hour soak', 'Android16 ARM64', 'zero memory leaks proven']}
    t0 = time.monotonic(); h0 = fixture.hits
    n = max(12, int(seconds/interval)+1)
    for i in range(n):
        until = t0+i*interval - time.monotonic()
        if until > 0: time.sleep(until)
        t = time.monotonic()
        s = {'sample': i, 'elapsedSec': round(t-t0, 3), 'fixtureHttpHits': fixture.hits,
             'unixTime': time.time(), 'sampleScheduleLagSec': max(0, round(t-(t0+i*interval), 3))}
        s['pidofRc'], pids = run(['adb','shell','pidof',PKG],timeout=14)
        s['pids'] = pids.strip()[:160]
        s['meminfoRc'], mem = run(['adb','shell','dumpsys','meminfo',PKG],timeout=30)
        s['pssKiB'] = _mem(mem) if s['meminfoRc'] == 0 else None
        if i in (0,3,6,9,n-1):
            (out/f'r123_meminfo_{i:02}.txt').write_text(mem[-25000:],encoding='utf8')
        probe = read_status(ws,tab_id,cdp)
        if probe['cdpOk']:
            s.update(status_fields(probe['status']))
        s.update({k:v for k,v in probe.items() if k != 'status'})
        annotate_sample(s,ws,cdp,n)
        report['samples'].append(s)
        print('R123_NATIVE_SAMPLE', json.dumps({k:s.get(k) for k in ('sample','elapsedSec','pssKiB','fixtureHttpHits','cdpOk','mode','storageUsage','storagePressure','errorClass')},ensure_ascii=False),flush=True)
    elapsed = time.monotonic()-t0
    vals = [s['pssKiB'] for s in report['samples'] if type(s.get('pssKiB')) is int]
    report['summary'] = {'durationSeconds': round(elapsed,2),'samples':len(report['samples']),
        'httpDelta':fixture.hits-h0, 'validPss':len(vals), 'peakPssKiB':max(vals) if vals else None,
        'first3MedianKiB':statistics.median(vals[:3]) if len(vals)>=3 else None,
        'last3MedianKiB':statistics.median(vals[-3:]) if len(vals)>=3 else None,
        'statusErrors':sum(not s.get('cdpOk') for s in report['samples']),
        'classifications': sorted(set(s.get('errorClass') for s in report['samples'] if s.get('errorClass')))}
    report['gates'] = evaluate_gates(report['samples'],fixture.hits-h0,elapsed,seconds)
    report['gates'].update(evaluate_diagnostic_gates(report['samples']))
    for k,v in report['gates'].items():
        state['gates'][k] = {'status':v['status'], 'detail':json.dumps(v['evidence'],ensure_ascii=False)[:1700]}
        print('R123_'+v['status']+' '+k+' '+json.dumps(v['evidence'],ensure_ascii=False)[:400],flush=True)
    report['gates']['R121-13_24h_soak']={'status':'NOT_RUN','evidence':'This was only '+str(round(elapsed))+' seconds; do not substitute for 24h'}
    report['gates']['R121-14_Android16']={'status':'NOT_RUN','evidence':'R123 native sampler targets Android11 official Kiwi x86_64 only'}
    with (out/'r123_android_soak.csv').open('w',newline='',encoding='utf8') as f:
        fields=sorted(set().union(*(s.keys() for s in report['samples'])))
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(report['samples'])
    (out/'r123_android_soak.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    return report
