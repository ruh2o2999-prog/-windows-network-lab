#!/usr/bin/env python3
"""Download and verify the official Kiwi x64 GitHub Release APK; keep failure evidence."""
import hashlib, json, subprocess, urllib.request, zipfile, traceback
from pathlib import Path

REPO='kiwibrowser/src.next'
TAG='14310011181'
OUT=Path('out')

def main():
    OUT.mkdir(exist_ok=True)
    req=urllib.request.Request('https://api.github.com/repos/'+REPO+'/releases/tags/'+TAG,
                              headers={'Accept':'application/vnd.github+json','User-Agent':'Kiwi-R101-Android-Lab'})
    with urllib.request.urlopen(req,timeout=40) as r:data=json.load(r)
    assets=data.get('assets',[])
    (OUT/'upstream_assets.json').write_text(json.dumps([{'name':x['name'],'size':x.get('size'),'url':x.get('browser_download_url')} for x in assets],indent=2))
    matches=[x for x in assets if '-x64-' in x['name'].lower() and x['name'].endswith('-github.apk')]
    if not matches:raise RuntimeError('Official '+TAG+' release has no x64 -github.apk; see upstream_assets.json')
    a=matches[0];apk=Path('kiwi-official-x64.apk')
    subprocess.run(['curl','-fL','--retry','4','--retry-delay','3','--connect-timeout','30','--output',str(apk),a['browser_download_url']],check=True,timeout=500)
    if apk.stat().st_size < 15_000_000:raise RuntimeError('APK unexpectedly small')
    with zipfile.ZipFile(apk) as z:
        if 'AndroidManifest.xml' not in z.namelist():raise RuntimeError('File is not a valid Android APK')
    manifest={'tag':TAG,'asset_name':a['name'],'asset_url':a['browser_download_url'],
              'bytes':apk.stat().st_size,'sha256':hashlib.sha256(apk.read_bytes()).hexdigest()}
    (OUT/'official_apk_manifest.json').write_text(json.dumps(manifest,indent=2))
    print('DOWNLOADED_OFFICIAL_KIWI',json.dumps(manifest),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as e:
        OUT.mkdir(exist_ok=True)
        (OUT/'official_apk_download_error.json').write_text(json.dumps({
            'status':'FAIL','reason':repr(e),'traceback':traceback.format_exc(),
            'source_repository':REPO,'release_tag':TAG},indent=2))
        print('OFFICIAL_APK_DOWNLOAD_FAIL',repr(e),flush=True)
        raise
