#!/usr/bin/env python3
"""R127: verify real resume on current Kiwi tab(s) after process restart.
A pre-restart tab ID may be invalid. HTTP traffic and automatic debugger state
must both be observed. This helper never changes extension business behavior.
"""
import json
import time

def verify_resume(eval_js, msg, fixture_url, fixture, old_id, *, sleep=time.sleep, attempts=24, interval=.75):
    evidence = {"oldTabId":old_id, "fixtureUrl":fixture_url, "events":[], "statusSamples":[]}
    tabs = eval_js("(async()=>new Promise((yes,no)=>chrome.tabs.query({},r=>"
                   "chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):"
                   "yes(r.map(t=>({id:t.id,url:t.url,active:t.active,status:t.status}))))))()")
    evidence['currentTabIds'] = [t.get('id') for t in tabs]
    eligible = [t for t in tabs if isinstance(t.get('id'), int)
                and str(t.get('url') or '').startswith(fixture_url)]
    before = fixture.hits
    if eligible:
        tab = eligible[0]
        actual_id = tab['id']
        if not tab.get('active'):
            command = "(async()=>new Promise((yes,no)=>chrome.tabs.update("+str(actual_id)+",{active:true},r=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):yes({id:r.id,url:r.url}))))()"
            evidence['activation'] = eval_js(command)
        evidence['tabAction'] = 'reuse-current-live-tab'
    else:
        command = "(async()=>new Promise((yes,no)=>chrome.tabs.create({url:"+json.dumps(fixture_url)+",active:true},r=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):yes({id:r.id,url:r.url}))))()"
        tab = eval_js(command)
        actual_id = tab['id']
        evidence['tabAction'] = 'create-real-http-tab-after-restart'
        evidence['createdTab'] = tab
    evidence['actualTabId'] = actual_id
    if not isinstance(actual_id,int) or actual_id<0:
        evidence['reason']='invalid-new-tab-id'
        return False,evidence
    for i in range(attempts):
        sleep(interval)
        hits = fixture.hits - before
        try:
            status=msg('R121_STATUS', {'tabId':actual_id})
            cap=(status or {}).get('capture') or {}
            evidence['statusSamples'].append({'i':i,'httpDelta':hits,'mode':cap.get('mode'),
                'automatic':cap.get('automatic'),'paused':cap.get('paused'),
                'activeCount':cap.get('activeCount'),'error':cap.get('lastControlError')})
            if hits>=3 and cap.get('mode')=='debugger' and cap.get('automatic') is True \
                    and cap.get('paused') is False and cap.get('activeCount',0)>=1:
                evidence['reason']='live-http-and-cdp-confirmed'
                evidence['httpDelta']=hits
                return True,evidence
        except Exception as exc:
            evidence['events'].append({'attempt':i,'statusError':repr(exc)})
    evidence['httpDelta']=fixture.hits-before
    evidence['reason']='no-corroborated-live-http-cdp-resume'
    return False,evidence
