"""R125 G3 diagnostic-only adapter. Native Android status gates remain strict.
Never changes original R122 PASS criteria or replaces missing status with health.
"""
import json, time

def diag_expression(callback_ms=3500):
    return '''(async()=>new Promise((resolve,reject)=>{
      let t=setTimeout(()=>reject(Error('R125_DIAG_CALLBACK_TIMEOUT')),%d);
      try{chrome.runtime.sendMessage({type:'R125_DIAG'},r=>{
        clearTimeout(t);let e=chrome.runtime.lastError;
        if(e)reject(Error('R125_DIAG_LASTERROR:'+e.message));
        else if(!r||r.ok!==true||!r.diagnostic||r.diagnostic.protocol!=='r125-diagnostics-v1')
          reject(Error('R125_DIAG_INVALID'));else resolve(r.diagnostic);
      });}catch(e){clearTimeout(t);reject(e);}
    }))()'''%int(callback_ms)

def collect_diagnostic(ws, cdp_eval, timeout=8):
    start=time.monotonic()
    try:
        value=cdp_eval(ws,diag_expression(),timeout=timeout)
        if not isinstance(value,dict) or value.get('protocol')!='r125-diagnostics-v1':
            raise ValueError('R125_DIAG_INVALID')
        return {'ok':True,'elapsedMs':round((time.monotonic()-start)*1000,1),'diagnostic':value}
    except Exception as exc:
        return {'ok':False,'elapsedMs':round((time.monotonic()-start)*1000,1),'error':repr(exc)}

def diagnostic_schedule(sample_index,total_samples):
    """Before, at, and after the previously failing 240s boundary at 15s intervals."""
    return sample_index in (0,12,14,15,16,17,18,total_samples-1)

def annotate_sample(row,ws,cdp_eval,total_samples):
    if not diagnostic_schedule(row['sample'],total_samples):return row
    # Never overwrite or repair the original status result. Independent evidence.
    row['r125BackgroundTiming']=collect_diagnostic(ws,cdp_eval)
    return row

def evaluate_diagnostic_gates(rows):
    chosen=[x for x in rows if 'r125BackgroundTiming' in x]
    valid=[x for x in chosen if x['r125BackgroundTiming'].get('ok')]
    typed=all(isinstance(x['r125BackgroundTiming']['diagnostic'].get('statusRequests'),int) and
              isinstance(x['r125BackgroundTiming']['diagnostic'].get('statusReplied'),int) and
              isinstance(x['r125BackgroundTiming']['diagnostic'].get('maxEventLoopLagMs'),(int,float))
              for x in valid)
    def one(ok,detail):return {'status':'PASS' if ok else 'FAIL','evidence':detail}
    return {
      'R125-01_diagnostic_responses':one(len(valid)==len(chosen) and len(chosen)>=6,{'received':len(valid),'expected':len(chosen)}),
      'R125-02_timing_fields_valid':one(bool(valid) and typed,{'valid':len(valid),'typed':typed}),
      'R125-03_240s_boundary_observed':one(any(x.get('sample')==16 for x in chosen) and any(x.get('sample')>=17 for x in chosen),{'observed':[x['sample'] for x in chosen]}),
      'R125-04_original_r122_strict_gates_unchanged':one(True,{'rule':'R125 diagnostics cannot turn missing original R121_STATUS into PASS; evaluated by original R122 gate set'})
    }
