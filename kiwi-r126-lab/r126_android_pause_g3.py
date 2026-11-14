#!/usr/bin/env python3
"""R126 G3: original MV2 panel UI + official Android Kiwi real clicks.
No synthetic observation result. Historical R122-07/08 remain open.
"""
import json,time,traceback,sys
from pathlib import Path
from r109_history_recovery import cdp_eval,probe_cdp

PKG="com.kiwibrowser.browser"
def execute(run,snapshot,state,ws,tid,extension_id,fixture_url,fixture,
            type_internal_url,find_extensions_via_kiwi_menu,out):
    out=Path(out);out.mkdir(exist_ok=True)
    result={"name":"R126 genuine Kiwi default-on / pause / refresh / restart",
            "scope":"official Kiwi Android11 x86_64","gates":{},"steps":[],"errors":[],
            "uncovered":["Android16 real phone","1 hour continuous soak","R122-07/08 at 240 seconds","YouTube 403"]}
    def gate(name,ok,e):
        stat="PASS" if ok else "FAIL"
        result["gates"][name]={"status":stat,"evidence":e}
        state["gates"][name]={"status":stat,"detail":json.dumps(e,ensure_ascii=False,default=str)[:1700]}
        print("R126_G3_"+stat+" "+name+" "+json.dumps(e,ensure_ascii=False,default=str)[:600],flush=True)
        return ok
    def log(name,val):result["steps"].append({"step":name,"value":val})
    def eval_js(s,timeout=15):return cdp_eval(ws,s,timeout=timeout)
    def msg(type_,extra=None,timeout=12):
        command=json.dumps(dict({"type":type_,"tabId":tid},**(extra or {})),ensure_ascii=False)
        js="""(async()=>new Promise((yes,no)=>{chrome.runtime.sendMessage(%s,r=>{
          const e=chrome.runtime.lastError;
          if(e)no(Error(e.message));else yes(r);});}))()"""%command
        return eval_js(js,timeout=timeout)
    def ui():
        return eval_js("""(()=>{
          const b=document.getElementById('toggle-monitor');
          const r=document.getElementById('r120-refresh-all');
          return {button:b?.textContent,aria:b?.getAttribute('aria-pressed'),
            buttonDisabled:b?.disabled,refreshVisible:!!r,
            status:document.getElementById('r126-observe-state')?.textContent,
            refreshStatus:document.getElementById('r120-refresh-busy')?.textContent,
            site:document.getElementById('site')?.textContent,
            page:location.href};
        })()""")
    def click(which):
        return eval_js("""(()=>{const b=document.getElementById(%s);
          if(!b||b.disabled)return {clicked:false};
          b.click();return {clicked:true};})()"""%json.dumps(which))
    def poll(expected,tries=18):
        seen=[]
        for i in range(tries):
            try:
                b=msg("R126_OBSERVE_STATUS");u=ui()
                seen.append({"enabled":b.get("autoEnabled"),"transition":b.get("transition"),
                     "error":b.get("error"),"button":u.get("button"),"uiStatus":u.get("status")})
                if b.get("autoEnabled") is expected and not b.get("transition") and not u.get("buttonDisabled"):
                    return b,u,seen
            except Exception as exc:seen.append({"error":repr(exc)})
            time.sleep(.7)
        return b if 'b' in locals() else {},u if 'u' in locals() else {},seen
    try:
        snap=ui()
        status=msg("R126_OBSERVE_STATUS")
        first=msg("R121_STATUS")
        log("initial",{"ui":snap,"status":status,"capture":first.get("capture")})
        gate("R126-01_default_on_and_toolbar",
            status.get("autoEnabled") is True and snap.get("button")=="暂停观察"
            and snap.get("refreshVisible") and first.get("capture",{}).get("automatic") is True,
            {"ui":snap,"status":status})
        pressed=click("toggle-monitor")
        paused,ui_pause,trace=poll(False)
        cap=msg("R121_STATUS").get("capture") or {}
        gate("R126-02_real_UI_pause_and_CDP_detach",
            pressed.get("clicked") and paused.get("paused") is True
            and ui_pause.get("button")=="继续观察" and cap.get("mode")=="paused"
            and cap.get("activeCount")==0 and cap.get("actualMode")!="debugger",
            {"clicked":pressed,"status":paused,"ui":ui_pause,"capture":cap,"trace":trace[-5:]})
        time.sleep(3)
        prior=msg("MONITOR_READ")
        before=prior.get("monitor") or {}
        before_count=before.get("eventCount",0)
        page_hits_before=fixture.hits
        time.sleep(5)
        later=msg("MONITOR_READ");after=later.get("monitor") or {}
        log("paused_count",{"before":before_count,"after":after.get("eventCount"),"fixtureHitsBefore":page_hits_before,"fixtureHitsAfter":fixture.hits})
        gate("R126-03_paused_no_new_monitor_event",
            paused.get("paused") is True and after.get("eventCount")==before_count and
            fixture.hits-page_hits_before>=8,
            {"monitorBefore":before_count,"monitorAfter":after.get("eventCount"),"pageHttpContinued":fixture.hits-page_hits_before})
        refresh=click("r120-refresh-all")
        time.sleep(5)
        refreshed=msg("R126_OBSERVE_STATUS");ui_refresh=ui()
        gate("R126-04_manual_global_refresh_independent",
            refresh.get("clicked") and refreshed.get("autoEnabled") is False and
            ui_refresh.get("button")=="继续观察",
            {"refreshClick":refresh,"status":refreshed,"ui":ui_refresh})
        gate("R126-05_historical_monitor_not_cleared",
            len(after.get("entries") or [])>=len(before.get("entries") or []) and
            (after.get("eventCount") or 0)>0,
            {"historyEntriesBefore":len(before.get("entries") or []),
             "historyEntriesAfter":len(after.get("entries") or []),"eventCount":after.get("eventCount")})
        # Real Android process force-stop and relaunch, then extension panel revisit.
        run(["adb","shell","am","force-stop",PKG],timeout=20)
        time.sleep(2)
        run(["adb","shell","monkey","-p",PKG,"-c","android.intent.category.LAUNCHER","1"],timeout=30)
        time.sleep(7)
        snapshot("r126_after_kiwi_force_stop_relaunch")
        # Original Kiwi native menu is the approved route; direct extension URL
        # is only a fallback after checking a real native manager path.
        native_ok=False;reopened=False;open_details=[]
        try:
            from r109_panel_entry_v8101 import open_original_panel
            panel_xml,evidence=open_original_panel(run,snapshot,type_internal_url,extension_id,
                                                   fixture_url,find_extensions_via_kiwi_menu)
            open_details.append(evidence)
            native_ok=bool(evidence.get("native_menu_navigated"))
        except Exception as e:open_details.append({"nativeRouteError":repr(e)})
        info=probe_cdp(run,out)
        target=info.get("_websocket_url")
        if not target:
            type_internal_url("chrome-extension://"+extension_id+"/panel.html","r126_restarted_panel_direct_fallback")
            info=probe_cdp(run,out);target=info.get("_websocket_url")
        reopened=bool(target)
        gate("R126-06_real_browser_restart_panel_reopened",reopened,
             {"managerRoute":native_ok,"details":open_details[-1:],"target":info.get("found_target")})
        if reopened:
            ws=target
            states=[]
            for i in range(24):
                try:
                    x=msg("R126_OBSERVE_STATUS")
                    states.append(x)
                    if x.get("hydrated") and not x.get("transition"):break
                except Exception as e:states.append({"error":repr(e)})
                time.sleep(.65)
            back=states[-1] if states else {}
            u=ui()
            cap=msg("R121_STATUS").get("capture") or {}
            gate("R126-07_paused_setting_persisted_after_restart",
                back.get("hydrated") is True and back.get("autoEnabled") is False
                and u.get("button")=="继续观察" and cap.get("activeCount")==0,
                {"state":back,"ui":u,"capture":cap,"poll":states[-4:]})
            resumed=click("toggle-monitor")
            enabled,u2,t2=poll(True)
            gate("R126-08_original_UI_resumes_automatic_observation",
                resumed.get("clicked") and enabled.get("autoEnabled") is True
                and u2.get("button")=="暂停观察",
                {"click":resumed,"status":enabled,"ui":u2,"poll":t2[-4:]})
            # Re-activate original real HTTP tab, without synthetic background events.
            try:
                js="(async()=>new Promise((yes,no)=>chrome.tabs.update("+str(tid)+",{active:true},r=>chrome.runtime.lastError?no(Error(chrome.runtime.lastError.message)):yes({id:r.id,url:r.url}))))()"
                ret=eval_js(js)
                log("reactivate_real_tab",ret)
            except Exception as exc:log("reactivate_real_tab_error",repr(exc))
            count=0;last=None
            for _ in range(20):
                time.sleep(.75)
                try:
                    last=msg("R121_STATUS")
                    if (last.get("capture") or {}).get("mode")=="debugger":
                        count+=1;break
                except Exception as exc:last={"error":repr(exc)}
            gate("R126-09_auto_CDP_resumes",count>0,{"last":last})
        else:
            for key in ["R126-07_paused_setting_persisted_after_restart",
                        "R126-08_original_UI_resumes_automatic_observation","R126-09_auto_CDP_resumes"]:
                state["gates"][key]={"status":"NOT_RUN","detail":"Original panel could not be reopened after authentic Android restart"}
                result["gates"][key]={"status":"NOT_RUN","evidence":"Original panel not reachable after restart"}
    except Exception as exc:
        result["errors"].append(repr(exc));result["traceback"]=traceback.format_exc()
        gate("R126-99_runner_exception",False,{"error":repr(exc)})
    finally:
        (out/"r126_real_android_g3.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding="utf8")
    return result
