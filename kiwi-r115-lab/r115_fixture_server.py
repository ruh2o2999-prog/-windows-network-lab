#!/usr/bin/env python3
"""R115 synthetic localhost-only MSE fixture, no proprietary site bytes."""
import argparse,base64,hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
PAGE=r'''<!doctype html><html lang="en"><meta charset="utf-8"><title>R115 Authorized MSE Fixture</title>
<h1>R115_MSE_FIXTURE_READY</h1><video id="r115-video" controls playsinline muted></video>
<p id="status">booting</p><script>
window.r115Info={status:'booting',blobUrl:null,appendCalls:0};
(async()=>{
 const video=document.querySelector('#r115-video');const status=document.querySelector('#status');
 if(!window.MediaSource){status.textContent='NO_MSE';r115Info.status='NO_MSE';return;}
 const mime='video/mp4; codecs="avc1.64000c, mp4a.40.2"';
 if(!MediaSource.isTypeSupported(mime)){status.textContent='UNSUPPORTED_CODEC';r115Info.status='UNSUPPORTED_CODEC';return;}
 const media=new MediaSource();const url=URL.createObjectURL(media);
 video.src=url;r115Info.blobUrl=url;
 media.addEventListener('sourceopen',()=>{
   try {const sb=media.addSourceBuffer(mime);r115Info.trackReady=true;r115Info.status='READY';status.textContent='R115_READY';
     window.r115Push=async function(){
       const b=new Uint8Array(await(await fetch('/r115/fixture.mp4',{cache:'no-store'})).arrayBuffer());
       r115Info.bytes=b.length;r115Info.appendCalls++;
       await new Promise((ok,no)=>{sb.addEventListener('updateend',()=>ok(),{once:true});sb.addEventListener('error',()=>no(Error('SB_ERROR')),{once:true});sb.appendBuffer(b);});
       media.endOfStream();r115Info.status='ENDED';status.textContent='R115_ENDED';
       return {ok:true,bytes:b.length,appendCalls:r115Info.appendCalls,mseReadyState:media.readyState,videoSrc:video.currentSrc,codec:mime};
     };
   }catch(e){status.textContent='SOURCE_BUFFER_FAIL';r115Info.status='SOURCE_BUFFER_FAIL';r115Info.reason=String(e);}
 },{once:true});
})().catch(e=>{r115Info.status='BOOT_FAILED';r115Info.reason=String(e)});
</script></html>'''
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=18765);ap.add_argument('--fixture',required=True);a=ap.parse_args()
 data=Path(a.fixture).read_bytes();assert len(data)==116985 and hashlib.sha256(data).hexdigest()=='1062cc5384f83cb737baa37b60ea9d852096aa900c0e06a5cb29df8d0e58c031'
 class H(BaseHTTPRequestHandler):
  def do_GET(self):
   url=self.path.split('?',1)[0]
   if url=='/r115/mse.html':body=PAGE.encode();mime='text/html; charset=utf-8';status=200
   elif url=='/r115/fixture.mp4':body=data;mime='video/mp4';status=200
   elif url=='/favicon.ico':body=b'';mime='text/plain';status=204
   else:body=b'not found';mime='text/plain';status=404
   self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers()
   if body:self.wfile.write(body)
  def log_message(self,*args):pass
 server=ThreadingHTTPServer(('127.0.0.1',a.port),H);print('R115_SYNTHETIC_MSE_READY',a.port,flush=True);server.serve_forever()
if __name__=='__main__':main()
