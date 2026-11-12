$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$folder=Join-Path $env:RUNNER_TEMP 'pub010-v8101-modal-probe'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$child=Join-Path $folder 'controlled_child.ps1'
@'
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
[void][System.Windows.Forms.MessageBox]::Show('Test-only safe modal; no product content','PUB010-BMCLICK-SMOKE',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Error)
exit 0
'@ | Set-Content -LiteralPath $child -Encoding UTF8
Add-Type -TypeDefinition @'
using System;using System.Text;using System.Runtime.InteropServices;
public static class ModalSmoke {
  public delegate bool EnumCb(IntPtr h,IntPtr extra);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumCb cb,IntPtr extra);
  [DllImport("user32.dll",SetLastError=true)] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
  [DllImport("user32.dll",EntryPoint="GetWindowTextW",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h,StringBuilder b,int cap);
  [DllImport("user32.dll")] public static extern IntPtr GetDlgItem(IntPtr h,int id);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h,uint msg,IntPtr wp,IntPtr lp);
}
'@
$p=$null;$found=$false;$clicked=$false
try{
  $p=Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-NonInteractive','-File',('"'+$child+'"')) -PassThru
  for($i=0;$i -lt 75;$i++){
    $p.Refresh()
    if($p.HasExited){throw 'Child exited without modal'}
    $windows=[System.Collections.Generic.List[IntPtr]]::new()
    $cb=[ModalSmoke+EnumCb]{param([IntPtr]$h,[IntPtr]$ex) [uint32]$pid=0;[void][ModalSmoke]::GetWindowThreadProcessId($h,[ref]$pid);if($pid -eq [uint32]$p.Id){$windows.Add($h)};return $true}
    [void][ModalSmoke]::EnumWindows($cb,[IntPtr]::Zero)
    foreach($w in $windows){
      $b=[System.Text.StringBuilder]::new(256)
      [void][ModalSmoke]::GetWindowText($w,$b,$b.Capacity)
      if($b.ToString() -ne 'PUB010-BMCLICK-SMOKE'){continue}
      $found=$true
      $ok=[ModalSmoke]::GetDlgItem($w,1)
      if($ok -eq [IntPtr]::Zero){throw 'Dialog IDOK button not found'}
      if(![ModalSmoke]::PostMessage($ok,0x00F5,[IntPtr]::Zero,[IntPtr]::Zero)){throw 'BM_CLICK could not be posted'}
      $clicked=$true
      break
    }
    if($clicked){break}
    Start-Sleep -Milliseconds 200
  }
  if(!$found -or !$clicked){throw 'Modal not found or BM_CLICK not delivered'}
  if(!$p.WaitForExit(10000)){throw 'BM_CLICK did not close modal'}
  if($p.ExitCode -ne 0){throw "Child exited with $($p.ExitCode)"}
  Write-Host 'PUB010_WINDOWS_NATIVE_BM_CLICK_MODAL_SMOKE_PASS'
}finally{
  if($p){$p.Refresh();if(!$p.HasExited){Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue}}
  if(Test-Path $folder){Remove-Item -LiteralPath $folder -Recurse -Force -ErrorAction SilentlyContinue}
}
