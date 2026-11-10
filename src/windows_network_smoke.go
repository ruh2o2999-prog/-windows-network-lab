package main

import (
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "flag"
 "fmt"
 "io"
 "net"
 "net/http"
 "os"
 "path/filepath"
 "runtime"
 "time"
)

type Probe struct {
 Test string `json:"test"`
 URL string `json:"url"`
 Passed bool `json:"passed"`
 DNS []string `json:"dns_addresses,omitempty"`
 HTTPStatus int `json:"http_status,omitempty"`
 Bytes int `json:"download_bytes,omitempty"`
 SHA256 string `json:"sha256,omitempty"`
 Error string `json:"error,omitempty"`
 DurationMs int64 `json:"duration_ms"`
}
type Report struct {
 Timestamp string `json:"timestamp_utc"`
 Platform string `json:"platform"`
 Architecture string `json:"arch"`
 Overall string `json:"overall"`
 Probes []Probe `json:"probes"`
}

func runProbe(url, output string) Probe {
 start:=time.Now()
 p:=Probe{Test:"dns_https_download", URL:url}
 defer func(){ p.DurationMs=time.Since(start).Milliseconds() }()
 ips,err:=net.LookupIP("example.com")
 if err!=nil {p.Error="DNS: "+err.Error();return p}
 for _,ip:=range ips {p.DNS=append(p.DNS,ip.String())}
 client:=&http.Client{Timeout:30*time.Second}
 resp,err:=client.Get(url)
 if err!=nil {p.Error="HTTPS: "+err.Error();return p}
 defer resp.Body.Close()
 p.HTTPStatus=resp.StatusCode
 data,err:=io.ReadAll(io.LimitReader(resp.Body,1024*1024+1))
 if err!=nil {p.Error="READ: "+err.Error();return p}
 if len(data)>1024*1024 {p.Error="response_over_1MiB";return p}
 p.Bytes=len(data)
 sum:=sha256.Sum256(data)
 p.SHA256=hex.EncodeToString(sum[:])
 if p.HTTPStatus!=200 || p.Bytes<100 {p.Error=fmt.Sprintf("unexpected status %d or body size %d",p.HTTPStatus,p.Bytes);return p}
 if err:=os.WriteFile(filepath.Join(output,"example_html.html"),data,0644);err!=nil {p.Error="WRITE: "+err.Error();return p}
 p.Passed=true
 return p
}

func main(){
 out:=flag.String("out","evidence","Evidence directory")
 gui:=flag.Bool("gui",false,"Show result dialog")
 flag.Parse()
 if err:=os.MkdirAll(*out,0755);err!=nil {os.Exit(3)}
 result:=runProbe("https://example.com/",*out)
 report:=Report{Timestamp:time.Now().UTC().Format(time.RFC3339),Platform:runtime.GOOS,Architecture:runtime.GOARCH,Overall:"FAIL",Probes:[]Probe{result}}
 if result.Passed {report.Overall="PASS"}
 b,_:=json.MarshalIndent(report,"","  ")
 _=os.WriteFile(filepath.Join(*out,"network_report.json"),b,0644)
 fmt.Println(string(b))
 if *gui {popup("Windows HTTPS: "+report.Overall,fmt.Sprintf("HTTP: %d, bytes: %d",result.HTTPStatus,result.Bytes))}
 if !result.Passed {os.Exit(1)}
}
