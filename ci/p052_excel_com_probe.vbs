Option Explicit
' P052 nonprivate Windows COM probe; never changes Office settings.
Dim app, errNo, errSource, errText
Set app = Nothing
On Error Resume Next
Err.Clear
Set app = CreateObject("Excel.Application")
errNo = Err.Number
errSource = Err.Source
errText = Err.Description
Err.Clear
If errNo <> 0 Or app Is Nothing Then
    WScript.Echo "P052_EXCEL_COM=NOT_AVAILABLE"
    WScript.Echo "P052_COM_SIGNED=" & CStr(errNo)
    WScript.Echo "P052_COM_HEX=" & Hex(errNo)
    WScript.Echo "P052_COM_ERROR_SOURCE=" & errSource
    WScript.Quit 13
End If
WScript.Echo "P052_EXCEL_COM=INSTANTIATED"
WScript.Echo "P052_EXCEL_VERSION=" & CStr(app.Version)
app.Quit
Set app = Nothing
WScript.Quit 0
