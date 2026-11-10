//go:build windows
package main
import ("syscall";"unsafe")
func popup(title,message string) {
  t,_:=syscall.UTF16PtrFromString(title)
  s,_:=syscall.UTF16PtrFromString(message)
  u:=syscall.NewLazyDLL("user32.dll")
  _,_,_=u.NewProc("MessageBoxW").Call(0,uintptr(unsafe.Pointer(s)),uintptr(unsafe.Pointer(t)),0x40)
}
