$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Join-Path $env:RUNNER_TEMP 'pub032v5'
$source = Join-Path $root 'synthetic_34_input.zip'
$exe = Join-Path $root 'publisher.exe'
$expected = Get-Content (Join-Path $root 'expected.json') -Raw | ConvertFrom-Json
$outDir = Join-Path (Get-Location) 'out'
New-Item -ItemType Directory -Force $outDir | Out-Null
$outExe = Join-Path $outDir 'PUB032_V2113_34_SYNTH_INSTALL.exe'
$trace = [System.Collections.Generic.List[object]]::new()
$successPopup = $false
$errorPopup = $false
$detectedCount34 = $false
$acceptedConfirm = $false
$beforeSHA = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant()
if($beforeSHA -ne $expected.publisher_sha256) { throw 'Publisher byte identity mismatch' }
if((Get-FileHash $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.test_input_sha256){throw 'Source zip bytes mismatch'}
if($expected.expected_count -ne 34 -or $expected.genuine_P050_content_used -or $expected.genuine_V21128_content_used) { throw 'Fixture provenance invalid' }
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class PUB032V5Win {
  public delegate bool EnumCallback(IntPtr h,IntPtr extra);
  [DllImport("user32.dll",SetLastError=true)] public static extern bool EnumThreadWindows(uint id,EnumCallback cb,IntPtr extra);
  [DllImport("user32.dll",EntryPoint="GetClassNameW",CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h,StringBuilder x,int n);
  [DllImport("user32.dll",EntryPoint="GetWindowTextW",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h,StringBuilder x,int n);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr GetDlgItem(IntPtr h,int id);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] [return:MarshalAs(UnmanagedType.Bool)] public static extern bool SetWindowText(IntPtr h,string s);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr h,uint msg,IntPtr wp,IntPtr lp);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] [return:MarshalAs(UnmanagedType.Bool)] public static extern bool PostMessage(IntPtr h,uint msg,IntPtr wp,IntPtr lp);
}
'@
function List-Windows($process){
  $handles=[System.Collections.Generic.List[System.IntPtr]]::new()
  $callback=[PUB032V5Win+EnumCallback]{param([IntPtr]$h,[IntPtr]$extra) $handles.Add($h);return $true}
  $process.Refresh()
  foreach($t in $process.Threads){[void][PUB032V5Win]::EnumThreadWindows([uint32]$t.Id,$callback,[IntPtr]::Zero)}
  $rows=@()
  foreach($h in $handles){
    $cls=[System.Text.StringBuilder]::new(256)
    $txt=[System.Text.StringBuilder]::new(1024)
    [void][PUB032V5Win]::GetClassName($h,$cls,$cls.Capacity)
    [void][PUB032V5Win]::GetWindowText($h,$txt,$txt.Capacity)
    $rows+= [pscustomobject]@{handle=$h;class=$cls.ToString();title=$txt.ToString()}
  }
  return $rows
}
function Set-Edit($h,[int]$id,[string]$value){
  $ctl=[PUB032V5Win]::GetDlgItem($h,$id)
  if($ctl -eq [IntPtr]::Zero){throw "Publisher control missing: $id"}
  if(![PUB032V5Win]::SetWindowText($ctl,$value)){throw "SetWindowText failed: $id"}
}
$p=$null;$main=[IntPtr]::Zero
try {
  if(Test-Path $outExe){throw 'Refuse overwrite existing generated EXE'}
  $p=Start-Process -FilePath $exe -WorkingDirectory $root -PassThru
  for($i=0;$i -lt 35;$i++){
    if($p.HasExited){throw "Publisher exited before GUI, code=$($p.ExitCode)"}
    $windows=@(List-Windows $p)
    foreach($w in $windows){if($w.class -eq 'WorkPlatformPublisher'){$main=$w.handle}}
    if($main -ne [IntPtr]::Zero){break}
    Start-Sleep -Seconds 1
  }
  if($main -eq [IntPtr]::Zero){throw 'Publisher real GUI not found by EnumThreadWindows'}
  $trace.Add(@{kind='publisher_window_found';main_hwnd=$main.ToInt64()})
  Set-Edit $main 105 'PUB032_Synth34'
  Set-Edit $main 121 'PUB032_Synth34'
  Set-Edit $main 106 '0.1.0'
  Set-Edit $main 103 $source
  Set-Edit $main 107 $outExe
  $preset=[PUB032V5Win]::GetDlgItem($main,119)
  if($preset -eq [IntPtr]::Zero){throw 'Missing install preset combo'}
  [void][PUB032V5Win]::SendMessage($preset,0x014E,[IntPtr]1,[IntPtr]::Zero)
  [void][PUB032V5Win]::PostMessage($main,0x0111,[IntPtr]65655,$preset) # CBN_SELCHANGE(1) + ID 119
  $trace.Add(@{kind='publisher_fields_entered';input_source=$source;output_path=$outExe;preset='@WF:USERPROGRAMS'})
  if(![PUB032V5Win]::PostMessage($main,0x0111,[IntPtr]112,[IntPtr]::Zero)){throw 'Failed to post real ID_BUILD command'}
  $trace.Add(@{kind='posted_build_button'})
  for($i=0;$i -lt 180;$i++){
    if($p.HasExited){throw "Publisher process exited during GUI build: $($p.ExitCode)"}
    $windows=@(List-Windows $p)
    foreach($w in $windows){
      if($w.class -ne '#32770'){continue}
      if($w.title -eq '自动识别结果'){
        $trace.Add(@{kind='source_recognition';title=$w.title;result='IDYES'})
        if(![PUB032V5Win]::PostMessage($w.handle,0x0111,[IntPtr]6,[IntPtr]::Zero)){throw 'Failed to confirm source recognition'}
        $acceptedConfirm=$true
      }elseif($w.title -eq '确认免附加校验打包'){
        $trace.Add(@{kind='unexpected_emergency_prompt';title=$w.title})
        throw 'Unexpected emergency check disabled; fail closed'
      }elseif($w.title -eq '生成完成'){
        $trace.Add(@{kind='publish_success_modal';title=$w.title})
        $successPopup=$true
        [void][PUB032V5Win]::PostMessage($w.handle,0x0111,[IntPtr]1,[IntPtr]::Zero)
      }elseif($w.title -match '失败|错误|不足|不支持|取消|异常'){
        $trace.Add(@{kind='error_modal';title=$w.title})
        $errorPopup=$true
        throw "Publisher error modal: $($w.title)"
      }
    }
    if($successPopup -and (Test-Path $outExe) -and (Get-Item $outExe).Length -gt 100000){break}
    Start-Sleep -Seconds 1
  }
  if(!$acceptedConfirm){throw 'Never observed / accepted real source confirmation dialog'}
  if(!$successPopup){throw 'Never observed real published-success dialog'}
  if(!(Test-Path $outExe)){throw 'No real generated install EXE'}
  $sha=(Get-FileHash $outExe -Algorithm SHA256).Hash.ToLowerInvariant()
  $trace.Add(@{kind='generated_installer_exists';bytes=(Get-Item $outExe).Length;sha256=$sha})
  $report=[ordered]@{
    run='PUB032 V2.11.3 real publisher Windows GUI'
    product_version='V2.11.3 (older development branch, not V2.11.2.8)'
    genuine_P050_content_used=$false
    genuine_P050_34_file_names_synthetic_content=$true
    publisher_sha256_verified=$true
    native_windows_gui_started=$true
    actual_gui_build_submitted=$true
    actual_source_recognition_confirmed=$acceptedConfirm
    actual_success_popup_seen=$successPopup
    actual_generated_install_exe=$true
    generated_install_exe_sha256=$sha
    generated_install_exe_bytes=(Get-Item $outExe).Length
    new_version_V21128_tested=$false
    trace=$trace
  }
  $report | ConvertTo-Json -Depth 9 | Set-Content (Join-Path $outDir 'pub032_v2113_publisher_report.json') -Encoding utf8
  Write-Host 'PUB032_V2113_REAL_PUBLISHER_GUI_GENERATED_INSTALLER'
} finally {
  if($p -and !$p.HasExited){if($main -ne [IntPtr]::Zero){[void][PUB032V5Win]::PostMessage($main,0x0010,[IntPtr]::Zero,[IntPtr]::Zero)};Start-Sleep -Seconds 1; if(!$p.HasExited){Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue}}
  $trace | ConvertTo-Json -Depth 9 | Set-Content (Join-Path $outDir 'pub032_v2113_gui_trace.json') -Encoding utf8
}