#!/usr/bin/env python3
"""Separate host DNS/HTTPS, TLS and proxy failure classification; no secrets in artifact."""
import datetime,json,os,pathlib,socket,ssl,urllib.request,urllib.error,time
urls=["https://api.github.com/","https://dl.google.com/android/repository/repository2-1.xml","https://repo.maven.apache.org/maven2/","https://example.com/"]
r={"schema":"NET_HOST_v11","timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
   "checks":[],"proxy_env_present":[n for n in ("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY") if os.getenv(n)]}
for url in urls:
 host=urllib.request.urlparse(url).hostname
 row={"url":url,"dns":"NOT_RUN","https":"NOT_RUN"}
 try:
  addrs=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
  row["dns"]="PASS";row["resolved_count"]=len(addrs)
 except Exception as e:
  row.update(dns="FAIL",classification="DNS_FAILURE",error=type(e).__name__);r["checks"].append(row);continue
 try:
  q=urllib.request.Request(url,headers={"User-Agent":"coldboot-v11"},method="HEAD")
  with urllib.request.urlopen(q,timeout=10,context=ssl.create_default_context()) as f:
   row["http_status"]=f.status;row["https"]="PASS" if f.status in range(200,400) else "FAIL"
 except urllib.error.HTTPError as e:row.update(https="HTTP_STATUS",http_status=e.code)
 except Exception as e:
  row.update(https="FAIL",classification=("TLS_FAILURE" if isinstance(e,ssl.SSLError) else "ROUTE_PROXY_OR_TLS"),error=type(e).__name__)
 r["checks"].append(row)
r["host_network"] = "PASS" if sum(x["https"]=="PASS" for x in r["checks"])>=2 else "BLOCKED"
out=pathlib.Path("out/coldboot_v11/NET_host.json");out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(r,ensure_ascii=False,indent=2))
print(json.dumps({"host_network":r["host_network"],"checks":r["checks"]}))
