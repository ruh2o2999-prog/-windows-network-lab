$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Join-Path $env:RUNNER_TEMP 'pub032v21128'
$source = Join-Path $root 'source_p050_34.zip'
$exe = Join-Path $root 'publisher.exe'
$expected = Get-Content (Join-Path $root 'expected.json') -Raw | ConvertFrom-Json
$outDir = Join-Path (Get-Location) 'out'
New-Item -ItemType Directory -Force $outDir | Out-Null
$outExe = Join-Path $outDir 'PUB032_V21128_34_REAL_P050_INSTALL.exe'
$trace = [System.Collections.Generic.List[object]]::new()
$successPopup = $false
$errorPopup = $false
$detectedCount34 = $false
$acceptedConfirm = $false
$beforeSHA = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant()
if($beforeSHA -ne $expected.publisher_sha256) { throw 'Publisher byte identity mismatch' }
if((Get-FileHash $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.source_zip_sha256){throw 'Source zip bytes mismatch'}
if($expected.expected_count -ne 34 -or $expected.original_P050_test_fixture -ne $true -or $expected.version -ne 'V2.11.2.8') { throw 'Real P050 fixture and version provenance invalid' }
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
  // The official Win32 API expressly forbids SetWindowText on another process's EDIT control.
  // WM_SETTEXT and WM_GETTEXT are < WM_USER and Windows marshals them across processes.
  [DllImport("user32.dll",EntryPoint="SendMessageW",CharSet=CharSet.Unicode)]
  public static extern IntPtr SendMessageText(IntPtr h,uint msg,IntPtr wp,[MarshalAs(UnmanagedType.LPWStr)] string lp);
  [DllImport("user32.dll",EntryPoint="SendMessageW",CharSet=CharSet.Unicode)]
  public static extern IntPtr SendMessageBuilder(IntPtr h,uint msg,IntPtr wp,StringBuilder lp);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] [return:MarshalAs(UnmanagedType.Bool)] public static extern bool PostMessage(IntPtr h,uint msg,IntPtr wp,IntPtr lp);
  [DllImport("user32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] public static extern bool EnumChildWindows(IntPtr parent,EnumCallback cb,IntPtr extra);
  [DllImport("user32.dll",SetLastError=true)] public static extern int GetDlgCtrlID(IntPtr child);
  [DllImport("user32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] public static extern bool IsWindowEnabled(IntPtr h);
  [DllImport("user32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] public static extern bool IsWindowVisible(IntPtr h);
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
  # Never use SetWindowTextW for an EDIT in the separate publisher process.
  # Send synchronous WM_SETTEXT (0x000C) through Win32 system-message marshalling.
  $result=[PUB032V5Win]::SendMessageText($ctl,0x000C,[IntPtr]::Zero,$value)
  if($result -eq [IntPtr]::Zero){throw "Native WM_SETTEXT failed for field $id"}
  $actual=Read-WindowText $ctl
  if($actual -ne $value){throw "Native cross-process WM_GETTEXT readback mismatch for field $id"}
}

# PUB032 V6: nonintrusive, read-only diagnostics. Windows GUI always owns the actual build.
function Read-WindowText([IntPtr]$h) {
  if($h -eq [IntPtr]::Zero){return ''}
  $b=[System.Text.StringBuilder]::new(2048)
  [void][PUB032V5Win]::SendMessageBuilder($h,0x000D,[IntPtr]$b.Capacity,$b)
  return $b.ToString()
}
function Capture-Windows($proc,[IntPtr]$mainH,[int]$tick) {
  $top=@(List-Windows $proc)
  $rows=@()
  foreach($w in $top) {
    $childrenList=[System.Collections.Generic.List[System.IntPtr]]::new()
    $childrenCallback=[PUB032V5Win+EnumCallback]{param([IntPtr]$h,[IntPtr]$unused) $childrenList.Add($h);return $true}
    [void][PUB032V5Win]::EnumChildWindows($w.handle,$childrenCallback,[IntPtr]::Zero)
    $children=@()
    foreach($child in $childrenList) {
      $type=[System.Text.StringBuilder]::new(160)
      [void][PUB032V5Win]::GetClassName($child,$type,$type.Capacity)
      $children+=@{
        id=[PUB032V5Win]::GetDlgCtrlID($child)
        class=$type.ToString()
        text=(Read-WindowText $child)
        enabled=[PUB032V5Win]::IsWindowEnabled($child)
        visible=[PUB032V5Win]::IsWindowVisible($child)
      }
    }
    $rows+=@{
      title=$w.title
      class=$w.class
      hwnd=$w.handle.ToInt64()
      visible=[PUB032V5Win]::IsWindowVisible($w.handle)
      children=$children
    }
  }
  $statusControl=[PUB032V5Win]::GetDlgItem($mainH,113)
  $buildControl=[PUB032V5Win]::GetDlgItem($mainH,112)
  return @{
    kind='gui_snapshot'
    tick=$tick
    status=(Read-WindowText $statusControl)
    build_button_enabled=($buildControl -ne [IntPtr]::Zero -and [PUB032V5Win]::IsWindowEnabled($buildControl))
    output_exists=(Test-Path $outExe)
    windows=$rows
  }
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
  # Wait for WM_CREATE to finish creating real controls: top-level HWND can exist earlier.
  $required=@(103,105,106,107,112,119,121)
  $missing=$required
  for($ready=0;$ready -lt 45;$ready++){
    $missing=@($required | Where-Object { [PUB032V5Win]::GetDlgItem($main,[int]$_) -eq [IntPtr]::Zero })
    if($missing.Count -eq 0){break}
    Start-Sleep -Seconds 1
  }
  $trace.Add(@{kind='publisher_control_ready_scan';wait_cycles=$ready;missing_ids=@($missing)})
  if($missing.Count -ne 0){
    $childHandles=[System.Collections.Generic.List[System.IntPtr]]::new()
    $cb=[PUB032V5Win+EnumCallback]{param([IntPtr]$h,[IntPtr]$extra) $childHandles.Add($h);return $true}
    [void][PUB032V5Win]::EnumChildWindows($main,$cb,[IntPtr]::Zero)
    $children=@()
    foreach($h in $childHandles){
      $cc=[System.Text.StringBuilder]::new(256)
      [void][PUB032V5Win]::GetClassName($h,$cc,$cc.Capacity)
      $children+=@{id=[PUB032V5Win]::GetDlgCtrlID($h);class=$cc.ToString();handle=$h.ToInt64()}
    }
    $trace.Add(@{kind='publisher_child_window_diagnostics';controls=$children;count=$children.Count})
    throw "Publisher controls incomplete after 45 seconds. Missing=$($missing -join ',') ChildCount=$($children.Count)"
  }
  Set-Edit $main 105 'PUB032_P050_Test'
  Set-Edit $main 121 'PUB032_P050_Test'
  Set-Edit $main 106 '0.1.0'
  Set-Edit $main 103 $source
  Set-Edit $main 107 $outExe
  $preset=[PUB032V5Win]::GetDlgItem($main,119)
  if($preset -eq [IntPtr]::Zero){throw 'Missing install preset combo'}
  [void][PUB032V5Win]::SendMessage($preset,0x014E,[IntPtr]1,[IntPtr]::Zero)
  [void][PUB032V5Win]::PostMessage($main,0x0111,[IntPtr]65655,$preset) # CBN_SELCHANGE(1) + ID 119
  $trace.Add(@{kind='publisher_fields_entered';input_source=$source;output_path=$outExe;preset='@WF:USERPROGRAMS'})
  # Second run: verify the actual native edit-control bytes BEFORE submitting a UI button click.
  # The first run's inputs appeared populated externally but the publisher reported incomplete info.
  Start-Sleep -Milliseconds 1200
  $fieldIds=@(103,105,121,106,107)
  $readback=@{}
  foreach($id in $fieldIds) {
    $control=[PUB032V5Win]::GetDlgItem($main,[int]$id)
    if($control -eq [IntPtr]::Zero){throw "Native field missing before click: $id"}
    $readback["$id"]=Read-WindowText $control
  }
  $trace.Add(@{kind='native_edit_readback_before_click';fields=$readback})
  if($readback['103'] -ne $source -or $readback['105'] -ne 'PUB032_P050_Test' -or $readback['121'] -ne 'PUB032_P050_Test' -or $readback['106'] -ne '0.1.0' -or $readback['107'] -ne $outExe) {
    throw ('Readback mismatch before native BM_CLICK: '+($readback|ConvertTo-Json -Compress))
  }
  $buildButton=[PUB032V5Win]::GetDlgItem($main,112)
  if(![PUB032V5Win]::IsWindowEnabled($buildButton)){throw 'Native Build button disabled BEFORE click'}
  # Actual BM_CLICK on the real Windows button, not a synthetic WM_COMMAND injection.
  if(![PUB032V5Win]::PostMessage($buildButton,0x00F5,[IntPtr]::Zero,[IntPtr]::Zero)){
    throw 'PostMessage(BM_CLICK) to native Build button failed'
  }
  $trace.Add(@{kind='posted_native_button_BM_CLICK';enabled=[PUB032V5Win]::IsWindowEnabled($buildButton);status=(Read-WindowText ([PUB032V5Win]::GetDlgItem($main,113)))})
  # Diagnose every visible modal, not just two hard-coded titles.
  # A synthetic workbook may legitimately fail strict validation; never bypass that gate to make CI green.
  $seenDialog=[System.Collections.Generic.HashSet[string]]::new()
  for($i=0;$i -lt 180;$i++){
    $p.Refresh()
    if($p.HasExited){throw "Publisher process exited during GUI build: $($p.ExitCode)"}
    if(($i % 5) -eq 0){
      $snapshot=Capture-Windows $p $main $i
      $trace.Add($snapshot)
      Write-Host ("PUB032_GUI_SNAPSHOT tick={0} status={1} build_enabled={2} out_exists={3}" -f $i,$snapshot.status,$snapshot.build_button_enabled,$snapshot.output_exists)
    }
    $windows=@(List-Windows $p)
    foreach($w in $windows){
      if($w.class -ne '#32770' -or ![PUB032V5Win]::IsWindowVisible($w.handle)){continue}
      $fingerprint="$($w.handle.ToInt64()):$($w.title)"
      if($seenDialog.Add($fingerprint)){
        $trace.Add(@{kind='modal_window_observed';title=$w.title;hwnd=$w.handle.ToInt64();tick=$i})
        Write-Host ("PUB032_VISIBLE_MODAL title={0} hwnd={1}" -f $w.title,$w.handle.ToInt64())
      }
      if($w.title -eq '自动识别结果'){
        if(!$acceptedConfirm){
          $trace.Add(@{kind='source_recognition';title=$w.title;result='IDYES'})
          if(![PUB032V5Win]::PostMessage($w.handle,0x0111,[IntPtr]6,[IntPtr]::Zero)){
            throw 'Failed to confirm source recognition'
          }
          $acceptedConfirm=$true
        }
      }elseif($w.title -eq '安装资源与依赖预览'){
        $trace.Add(@{kind='actual_resource_preview';title=$w.title;action='KEEP_ALL_ID6701'})
        $keep=[PUB032V5Win]::GetDlgItem($w.handle,6701)
        if($keep -eq [IntPtr]::Zero){throw 'Actual resource preview lacks KEEP_ALL button ID6701'}
        if(![PUB032V5Win]::PostMessage($w.handle,0x0111,[IntPtr]6701,[IntPtr]::Zero)){throw 'Failed to select explicit KEEP ALL option'}
      }elseif($w.title -eq '生成完成'){
        $trace.Add(@{kind='publish_success_modal';title=$w.title})
        $successPopup=$true
        [void][PUB032V5Win]::PostMessage($w.handle,0x0111,[IntPtr]1,[IntPtr]::Zero)
      }else{
        # Unexpected modal: preserve first, fail closed. Do NOT click arbitrary consent/error dialogs.
        $trace.Add((Capture-Windows $p $main $i))
        throw ("PUB032 unexpected visible modal: '{0}'. Check gui_trace and validation status; no automatic approval." -f $w.title)
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
    run='PUB032 V2.11.2.8 real publisher Windows GUI'
    product_version='V2.11.2.8 real baseline'
    genuine_P050_content_used=$true
    genuine_P050_34_file_names_synthetic_content=$false
    publisher_sha256_verified=$true
    native_windows_gui_started=$true
    actual_gui_build_submitted=$true
    actual_source_recognition_confirmed=$acceptedConfirm
    actual_success_popup_seen=$successPopup
    actual_generated_install_exe=$true
    generated_install_exe_sha256=$sha
    generated_install_exe_bytes=(Get-Item $outExe).Length
    new_version_V21128_tested=$true
    trace=$trace
  }
  $report | ConvertTo-Json -Depth 9 | Set-Content (Join-Path $outDir 'pub032_v21128_publisher_report.json') -Encoding utf8
  Write-Host 'PUB032_V21128_REAL_PUBLISHER_GUI_GENERATED_INSTALLER'
} finally {
  if($p -and !$p.HasExited){if($main -ne [IntPtr]::Zero){[void][PUB032V5Win]::PostMessage($main,0x0010,[IntPtr]::Zero,[IntPtr]::Zero)};Start-Sleep -Seconds 1; if(!$p.HasExited){Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue}}
  $trace | ConvertTo-Json -Depth 9 | Set-Content (Join-Path $outDir 'pub032_v21128_gui_trace.json') -Encoding utf8
}