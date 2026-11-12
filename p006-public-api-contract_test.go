package tun

// Public-only contract test: checks upstream signatures, not any unpublished
// Android protection implementation. No runtime network connection is made.
import (
 "context"
 "net"
 "testing"
 "cfa/native/app"
 nativeTunnel "cfa/native/tunnel"
 C "github.com/metacubex/mihomo/constant"
 P "github.com/metacubex/mihomo/constant/provider"
 coreTunnel "github.com/metacubex/mihomo/tunnel"
)
type p006ContractTunnel struct {
 P.Tunnel
 raw C.Tunnel
}
func (t *p006ContractTunnel) NatTable() C.NatTable { return t.raw.NatTable() }
func (t *p006ContractTunnel) HandleTCPConn(c net.Conn, m *C.Metadata) { t.raw.HandleTCPConn(c,m) }
func (t *p006ContractTunnel) HandleUDPPacket(p C.UDPPacket, m *C.Metadata) { t.raw.HandleUDPPacket(p,m) }
var _ C.Tunnel = (*p006ContractTunnel)(nil)
var _ P.Tunnel = (*p006ContractTunnel)(nil)
var _ func(net.Addr,net.Addr)int = app.QuerySocketUid
var _ func() = nativeTunnel.CloseAllConnections
var _ func() map[string]C.Proxy = coreTunnel.Proxies
func TestP006Contract(t *testing.T) {
 m:=(&C.Metadata{NetWork:C.TCP, Type:C.INNER, Host:"test.invalid", DstPort:443}).Clone()
 m.SpecialProxy="pinned-proxy-example"
 if m.SpecialProxy=="" { t.Fatal("metadata proxy field missing") }
 var proxy C.Proxy
 var conn net.Conn
 var err error
 if false { conn,err=proxy.DialContext(context.Background(),m) }
 _=conn;_ = err
 var pkt C.UDPPacket
 if false {pkt.Drop()}
}
