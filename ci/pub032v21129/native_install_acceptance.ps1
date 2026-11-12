# V2.11.2.9 RC1 Windows native installer acceptance.
# EXPLICIT LIMITATION: GitHub runner lacks licensed Excel; HKCU temporary file-presence shim
# tests only installer filesystem transactional behavior, NOT Excel macro/office compatibility.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root=Join-Path $env:RUNNER_TEMP 'pub032v21129'
$out=Join-Path (Get-Location) 'out'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$pkg34=Join-Path $out 'PUB032_V21129_34_REAL_P050_INSTALL.exe'
$pkg28=Join-Path $out 'PUB032_V21129_28_EXCLUDE_QA_INSTALL.exe'
$target=Join-Path $env:LOCALAPPDATA 'Programs\PUB032_P050_Test'
$excelStub=Join-Path $env:RUNNER_TEMP 'WF_TestOnly_Office15'
$regPath='HKCU:\SOFTWARE\Microsoft\Office\15.0\Excel\InstallRoot'
$results=[System.Collections.Generic.List[object]]::new()
$script:acceptanceError=''
$QA=@('RUN_P043_ALL_WIN7.cmd','RUN_P043_WIN7.cmd','RUN_P046_ALL_WIN7.cmd','RUN_P047_ALL_WIN7.cmd','RUN_P050_ALL_WIN7.cmd','RUN_P050_FORM_ONLY.cmd')
$expected=(Get-Content (Join-Path $root 'expected.json') -Raw -Encoding UTF8 | ConvertFrom-Json)
if($expected.version -ne 'V2.11.2.9' -or $expected.expected_count -ne 34){throw 'Wrong source expectation'}
if(Test-Path $target){throw 'Target already exists; refusing to overwrite anything'}
if(Test-Path $regPath){throw 'Excel mock registry location occupied; refusing to overwrite'}
if(!(Test-Path $pkg28) -or !(Test-Path $pkg34)){throw 'Actual generated installer EXEs absent'}
Add-Type -TypeDefinition @'
using System;using System.Collections.Generic;using System.Text;using System.Runtime.InteropServices;
public static class NativeWFInstallerTest {
  public delegate bool EnumCallback(IntPtr h, IntPtr arg);
  [DllImport("user32.dll", SetLastError=true)] public static extern bool EnumThreadWindows(uint id,EnumCallback cb,IntPtr extra);
  [DllImport("user32.dll",EntryPoint="GetClassNameW", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hwnd,StringBuilder sb,int cap);
  [DllImport("user32.dll",EntryPoint="GetWindowTextW", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd,StringBuilder sb,int cap);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr GetDlgItem(IntPtr hwnd,int id);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern bool PostMessage(IntPtr hwnd,uint msg,IntPtr wp,IntPtr lp);
  [DllImport("user32.dll",SetLastError=true)] public static extern bool IsWindowEnabled(IntPtr hwnd);
}
'@
function Enum-Windows($p){
  $p.Refresh();$list=[System.Collections.Generic.List[IntPtr]]::new()
  $cb=[NativeWFInstallerTest+EnumCallback]{param([IntPtr]$h,[IntPtr]$arg) $list.Add($h);return $true}
  foreach($t in $p.Threads){[void][NativeWFInstallerTest]::EnumThreadWindows([uint32]$t.Id,$cb,[IntPtr]::Zero)}
  $rows=@()
  foreach($h in $list){
    $c=[System.Text.StringBuilder]::new(180);$t=[System.Text.StringBuilder]::new(520)
    [void][NativeWFInstallerTest]::GetClassName($h,$c,$c.Capacity)
    [void][NativeWFInstallerTest]::GetWindowText($h,$t,$t.Capacity)
    $rows+=@{h=$h;class=$c.ToString();title=$t.ToString()}
  }
  return @($rows)
}
function Run-NativeInstaller([string]$path,[string]$label,[int]$expectedExit) {
  if(!(Test-Path $path)){throw "Missing real installer: $label"}
  $proc=Start-Process -FilePath $path -PassThru
  $clicked=$false;$errorSeen=$false;$errorTitle='';$closeSent=$false;$lastWindows=@()
  try{
    for($i=0;$i -lt 135;$i++){
      $proc.Refresh()
      if($proc.HasExited){break}
      $windows=@(Enum-Windows $proc)
      $lastWindows=@($windows | ForEach-Object {"$($_.class):$($_.title)"})
      if(($i%25) -eq 0){Write-Host "INSTALL_PROGRESS $label tick=$i clicked=$clicked modal=$errorSeen window_count=$($windows.Count)"}
      $main=@($windows | Where-Object {$_.class -eq 'WorkPlatformInstaller'} | Select-Object -First 1)
      if(!$clicked -and $main.Count){
        $h=$main[0].h
        if([NativeWFInstallerTest]::GetDlgItem($h,203) -ne [IntPtr]::Zero){
          if(![NativeWFInstallerTest]::PostMessage($h,0x0111,[IntPtr]203,[IntPtr]::Zero)){throw "Installer start click failed: $label"}
          $clicked=$true
        }
      }
      foreach($w in $windows){
        if($w.class -ne '#32770'){continue}
        if($w.title -eq '工作平台 · 安装失败'){
          if(!$errorSeen){Write-Host "INSTALL_MODAL_DETECTED $label title=$($w.title)"}
          $errorSeen=$true;$errorTitle=$w.title
          [void][NativeWFInstallerTest]::PostMessage($w.h,0x0111,[IntPtr]1,[IntPtr]::Zero)
        }else{throw "Unexpected installer modal for $label; title '$($w.title)' not approved"}
      }
      # Do not close owner while modal is active; show_failure() sets finished
      # only AFTER MessageBox returns. Wait for enabled close button and retry.
      $modalPresent=@($windows | Where-Object {$_.class -eq '#32770'}).Count -gt 0
      if($errorSeen -and !$modalPresent -and $main.Count -and (($i%4) -eq 0)){
        $h=$main[0].h
        $btn=[NativeWFInstallerTest]::GetDlgItem($h,203)
        if($btn -ne [IntPtr]::Zero -and [NativeWFInstallerTest]::IsWindowEnabled($btn)){
          [void][NativeWFInstallerTest]::PostMessage($h,0x0111,[IntPtr]203,[IntPtr]::Zero)
          $closeSent=$true
          Write-Host "INSTALL_FAIL_DIALOG_CLOSED $label post_close_tick=$i"
        }
      }
      Start-Sleep -Milliseconds 500
    }
    $proc.Refresh()
    if(!$proc.HasExited){throw "Timeout waiting for actual installer: $label;clicked=$clicked;error_modal=$errorSeen;windows=$($lastWindows -join ',')"}
    if(!$clicked){throw "Installer GUI never received ID_INSTALL command: $label"}
    $exit=[int]$proc.ExitCode
    $row=@{case=$label;process_exit=$exit;expected_exit=$expectedExit;native_gui_clicked=$clicked;error_modal_seen=$errorSeen;
      no_excel_business_macro_execution=$true;office_presence_test_shim_only=(Test-Path $regPath)}
    $results.Add($row)
    Write-Host "INSTALL_CASE $label EXIT=$exit expected=$expectedExit clicked=$clicked error_seen=$errorSeen"
    if($exit -ne $expectedExit){throw "Installer $label exit=$exit expected=$expectedExit"}
  }finally{
    $proc.Refresh()
    if(!$proc.HasExited){Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue}
  }
}
function Verify-Files([int]$expectedCount,[string]$label,[bool]$allowOldQa){
  $names=[System.Collections.Generic.List[string]]::new()
  $missing=[System.Collections.Generic.List[string]]::new()
  foreach($item in $expected.files.PSObject.Properties){
    $name=[string]$item.Name
    if($expectedCount -eq 28 -and $QA -contains $name){continue}
    $path=Join-Path $target ($name.Replace('/','\'))
    if(!(Test-Path -LiteralPath $path -PathType Leaf)){$missing.Add($name);continue}
    $got=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if($got -ne [string]$item.Value.sha256){throw "SHA drift for case $label : $name"}
    $names.Add($name)
  }
  if($missing.Count){throw "Missing deployed files in $label : $($missing.Count)"}
  if($names.Count -ne $expectedCount){throw "Matched count $($names.Count) expected $expectedCount"}
  $qa=@($QA | Where-Object {Test-Path -LiteralPath (Join-Path $target $_) -PathType Leaf})
  if(!$allowOldQa -and $expectedCount -eq 28 -and $qa.Count){throw "Fresh 28 install contains old QA CMD unexpectedly"}
  if(!(Test-Path -LiteralPath (Join-Path $target 'RUN_WANFANG_WORKBENCH.cmd'))){throw 'Runtime CMD was lost'}
  $templateCount=@($names | Where-Object {$_ -like 'DataTemplates/*'}).Count
  if($templateCount -ne 4){throw 'Four DataTemplates not present'}
  $results.Add(@{case=$label;matched_source_count=$names.Count;source_sha256_verified=$true;old_qa_present=$qa.Count;
    four_templates_present=$true;normal_runtime_cmd_present=$true})
  Write-Host "VERIFY_CASE $label matched=$($names.Count) qa_present=$($qa.Count)"
  return $qa.Count
}
function Snapshot-UserData {
  $check=@(
    @{p='Data\用户测试数据.bin';b='PRIVATE_TEST_20261112_NOT_REAL_DATA'},
    @{p='用户备注_升级保留测试.txt';b='NOT_REAL_DATA_KEEP_BYTE_IDENTICAL'}
  )
  foreach($row in $check){
    $path=Join-Path $target $row.p
    $folder=Split-Path $path -Parent
    New-Item -ItemType Directory -Force $folder | Out-Null
    [IO.File]::WriteAllBytes($path,[Text.Encoding]::UTF8.GetBytes($row.b))
  }
  return $check
}
function Verify-UserData($items,[string]$name){
  foreach($row in $items){
    $path=Join-Path $target $row.p
    if(!(Test-Path -LiteralPath $path -PathType Leaf) -or
      [IO.File]::ReadAllText($path) -cne $row.b){throw "User-owned data changed during $name"}
  }
  $results.Add(@{case=$name;private_test_data_unchanged=$true;checked_items=$items.Count})
}
try{
  # Negative install on a runner with no Office executable: protection must refuse.
  $possible=@(Get-ChildItem 'C:\Program Files\Microsoft Office','C:\Program Files (x86)\Microsoft Office' -Filter EXCEL.EXE -Recurse -ErrorAction SilentlyContinue)
  if($possible.Count){throw 'Cannot perform no-Office negative test: Office executable already present'}
  # Temporary mock only checks if filesystem installation & trust registry protocols execute.
  # This is NOT genuine Office/Excel and does not authorize any macro operations.
  New-Item -ItemType Directory -Force $excelStub | Out-Null
  Copy-Item (Join-Path $env:WINDIR 'System32\notepad.exe') (Join-Path $excelStub 'EXCEL.EXE') -ErrorAction Stop
  New-Item -Path $regPath -Force | Out-Null
  New-ItemProperty -Path $regPath -Name Path -Value ($excelStub + '\') -PropertyType String -Force | Out-Null
  Run-NativeInstaller $pkg28 'fresh28_native_install_office_presence_simulated' 0
  [void](Verify-Files 28 'fresh28_disk_sha' $false)
  $userData=Snapshot-UserData
  Run-NativeInstaller $pkg34 'upgrade28to34_native_install_office_presence_simulated' 0
  [void](Verify-Files 34 'upgrade34_disk_sha' $false)
  Verify-UserData $userData 'upgrade34_preserved_user_data'
  # Prior QA CMD will be treated as extra files by the v0.38.4 preservation path.
  Run-NativeInstaller $pkg28 'upgrade34to28_native_install_office_presence_simulated' 0
  $oldQaCount=Verify-Files 28 'upgrade28_disk_sha_and_qa_inventory' $true
  Verify-UserData $userData 'upgrade28_preserved_user_data'
  # Fault injection: deny rename on a real installed workbook. Existing user data must remain.
  $workbook=Join-Path $target 'wf_p042_candidate.xlsm'
  $oldDigest=(Get-FileHash -LiteralPath $workbook -Algorithm SHA256).Hash.ToLowerInvariant()
  $handle=[IO.File]::Open($workbook,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)
  try{Run-NativeInstaller $pkg28 'backup_locked_file_fail_closed' 3060}
  finally{$handle.Dispose()}
  $afterDigest=(Get-FileHash -LiteralPath $workbook -Algorithm SHA256).Hash.ToLowerInvariant()
  if($afterDigest -ne $oldDigest){throw 'Original workbook changed after locked-file failure'}
  Verify-UserData $userData 'failed_backup_original_data_unchanged'
  $results.Add(@{case='upgrade34to28_qa_retention';qa_cmd_remaining=$oldQaCount;needs_product_policy_decision=($oldQaCount -gt 0)})
  Write-Host "NATIVE_INSTALL_MAIN_CASES_COMPLETED;oldQA_retained=$oldQaCount"
  # Verify no-Office refusal LAST, after successful filesystem transaction cases.
  # Negative gate must not touch the already installed workbook.
  $beforeGate=(Get-FileHash -LiteralPath $workbook -Algorithm SHA256).Hash.ToLowerInvariant()
  if(Test-Path $regPath){Remove-Item -Path $regPath -Recurse -Force -ErrorAction Stop}
  Run-NativeInstaller $pkg28 'no_office_fail_closed' 2402
  $afterGate=(Get-FileHash -LiteralPath $workbook -Algorithm SHA256).Hash.ToLowerInvariant()
  if($beforeGate -ne $afterGate){throw 'No-Office refusal changed existing workbook'}
  Write-Host "NATIVE_INSTALL_ACCEPTANCE_COMPLETED;oldQA_retained=$oldQaCount"
}catch{
  $script:acceptanceError=$_.Exception.Message
  Write-Host "NATIVE_INSTALL_ACCEPTANCE_ERROR=$($script:acceptanceError)"
  throw
}finally{
  if(Test-Path $regPath){Remove-Item -Path $regPath -Recurse -Force -ErrorAction SilentlyContinue}
  if(Test-Path $excelStub){Remove-Item -LiteralPath $excelStub -Recurse -Force -ErrorAction SilentlyContinue}
  # Never remove existing user files outside our exact test installation target.
  @{version='V2.11.2.9 RC1';host='Windows Server 2022';
    office='SIMULATED FILE PRESENCE, NOT EXCEL';real_p050_input=$true;
    real_installers_executed=($results.Count -gt 0);true_excel_macro_tested=$false;
    cases=$results;overall=(!$script:acceptanceError);error=$script:acceptanceError} | ConvertTo-Json -Depth 10 |
    Set-Content (Join-Path $out 'pub032_v21129_native_install_acceptance.json') -Encoding UTF8
}
