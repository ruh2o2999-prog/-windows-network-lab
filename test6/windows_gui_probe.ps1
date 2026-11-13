param(
 [switch]$App,
 [string]$StatePath = "$env:RUNNER_TEMP\test6-gui-state.txt",
 [string]$ReportPath = "$env:RUNNER_TEMP\test6-win-gui-report.json"
)
$ErrorActionPreference='Stop'
$script:Test6SourcePath=$PSCommandPath
if ($App) {
 Add-Type -AssemblyName System.Windows.Forms
 Add-Type -AssemblyName System.Drawing
 $form=New-Object System.Windows.Forms.Form
 $form.Text='TEST6_REAL_WINDOWS_GUI'
 $form.Width=560;$form.Height=260;$form.StartPosition='CenterScreen'
 $box=New-Object System.Windows.Forms.TextBox
 $box.Left=28;$box.Top=28;$box.Width=480
 $box.Text='TEST6_REAL_WINDOWS_NATIVE_CLICK_PERSISTENCE'
 if (Test-Path $StatePath){$box.Text=Get-Content $StatePath -Raw}
 $button=New-Object System.Windows.Forms.Button
 $button.Left=28;$button.Top=90;$button.Width=260;$button.Height=48
 $button.Text='TEST6_SAVE_AND_EXIT'
 $button.Add_Click({[System.IO.File]::WriteAllText($StatePath,$box.Text,[System.Text.Encoding]::UTF8);$form.Close()})
 $form.Controls.Add($box);$form.Controls.Add($button)
 [void]$form.ShowDialog()
 exit 0
}
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class N {
 public delegate bool Callback(IntPtr h,IntPtr extra);
 [DllImport("user32.dll",SetLastError=true)] public static extern bool EnumThreadWindows(uint thread,Callback cb,IntPtr extra);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindow(string c,string title);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h,StringBuilder s,int max);
 [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h,int cmd);
 [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h,int msg,IntPtr w,IntPtr l);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 public static IntPtr ChildByText(IntPtr parent,string expected) {
   var b = new StringBuilder(200);
   for(IntPtr x=GetWindow(parent,5); x!=IntPtr.Zero; x=GetWindow(x,2)){
      b.Clear();GetWindowText(x,b,200);
      if(b.ToString()==expected)return x;
   }
   return IntPtr.Zero;
 }
}
'@
function Start-Gui {
 # Explicitly use caller script file, never function's invocation path
 $arg="-NoProfile -STA -ExecutionPolicy Bypass -File `"$script:Test6SourcePath`" -App -StatePath `"$StatePath`""
 return Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList $arg -PassThru -RedirectStandardOutput "$env:RUNNER_TEMP\test6-child-out.txt" -RedirectStandardError "$env:RUNNER_TEMP\test6-child-err.txt"
}
$report=[ordered]@{schema='test6-windows-gui-v1';os=$env:RUNNER_OS;gates=@{};scope='Synthetic WinForms control only, NOT user product EXE'}
function Gate([string]$n,[bool]$ok,[string]$detail) {$report.gates[$n]=@{status=$(if($ok){'PASS'}else{'FAIL'});detail=$detail};Write-Host "$n $ok"}
try {
 $proc=Start-Gui
 $w=[IntPtr]::Zero
 for($i=0;$i -lt 80;$i++){Start-Sleep -Milliseconds 300;$w=[N]::FindWindow($null,'TEST6_REAL_WINDOWS_GUI')
   if($w -eq [IntPtr]::Zero) {
    $proc.Refresh()
    $handles=New-Object 'System.Collections.Generic.List[System.IntPtr]'
    $callback=[N+Callback]{param([IntPtr]$h,[IntPtr]$extra) $handles.Add($h);return $true}
    foreach($thread in $proc.Threads) {[void][N]::EnumThreadWindows([uint32]$thread.Id,$callback,[IntPtr]::Zero)}
    foreach($h in $handles) {
     $title=New-Object System.Text.StringBuilder 256
     [void][N]::GetWindowText($h,$title,256)
     if($title.ToString() -eq 'TEST6_REAL_WINDOWS_GUI') {$w=$h;break}
    }
   }
   if($w -ne [IntPtr]::Zero){break}}
 $childDiag='';if(Test-Path "$env:RUNNER_TEMP\test6-child-err.txt"){$childDiag=Get-Content "$env:RUNNER_TEMP\test6-child-err.txt" -Raw}
 Gate 'real_winforms_window' ($w -ne [IntPtr]::Zero) ('Handle='+$w+' ProcExited='+$proc.HasExited+' ChildError='+$childDiag)
 if($w -eq [IntPtr]::Zero){throw 'WinForms window did not appear'}
 $b=[N]::ChildByText($w,'TEST6_SAVE_AND_EXIT')
 Gate 'real_button_handle' ($b -ne [IntPtr]::Zero) ('Handle='+$b)
 if($b -eq [IntPtr]::Zero){throw 'WinForms button did not appear'}
 [void][N]::SetForegroundWindow($w)
 [void][N]::SendMessage($b,0x00F5,[IntPtr]::Zero,[IntPtr]::Zero)
 for($i=0;$i -lt 50 -and !(Test-Path $StatePath);$i++){Start-Sleep -Milliseconds 200}
 $saved=(Test-Path $StatePath) -and ((Get-Content $StatePath -Raw).Trim() -eq 'TEST6_REAL_WINDOWS_NATIVE_CLICK_PERSISTENCE')
 Gate 'real_click_file_persist' $saved $StatePath
 if(!$saved){throw 'Click did not write expected file'}
 $sha=(Get-FileHash -Algorithm SHA256 $StatePath).Hash.ToLowerInvariant();$report.saved_sha256=$sha
 Gate 'saved_sha256' ($sha.Length -eq 64) $sha
 # Actual WinForms process will exit due button-click; check closed with timeout.
 $proc.WaitForExit(10000)|Out-Null
 Gate 'window_closed' $proc.HasExited ('ExitCode='+$(if($proc.HasExited){$proc.ExitCode}else{'RUNNING'}))
 $report.overall=if(@($report.gates.Values|Where-Object status -ne 'PASS').Count -eq 0){'PASS'}else{'FAIL'}
}catch {$report.error=$_.Exception.Message;$report.overall='FAIL'}
finally {
 if($proc -and !$proc.HasExited){Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue}
 $report|ConvertTo-Json -Depth 5|Out-File -Encoding utf8 $ReportPath
 Get-Content $ReportPath
 if($report.overall -ne 'PASS'){exit 2}
}
