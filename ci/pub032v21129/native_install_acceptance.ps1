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
$excelStub=Join-Path $env:RUNNER_TEMP 'WF_TestOnly\Office15'
# Real installer checks App Paths HKCU/HKLM, but Office\InstallRoot ONLY HKLM.
# Do not fabricate an unavailable Office service. This shim is only a controlled path-gate test.
$regPath='HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\excel.exe'
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
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr hwnd,uint msg,IntPtr wp,IntPtr lp);
  [DllImport("user32.dll",SetLastError=true)] public static extern bool EnumChildWindows(IntPtr hwnd,EnumCallback cb,IntPtr arg);
  [DllImport("user32.dll",SetLastError=true)] public static extern int GetDlgCtrlID(IntPtr hwnd);
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
function Capture-FailureModal([IntPtr]$dialog,[string]$label){
  $handles=[System.Collections.Generic.List[IntPtr]]::new()
  $cb=[NativeWFInstallerTest+EnumCallback]{param([IntPtr]$h,[IntPtr]$arg) $handles.Add($h);return $true}
  [void][NativeWFInstallerTest]::EnumChildWindows($dialog,$cb,[IntPtr]::Zero)
  $children=@()
  foreach($h in $handles){
    $buf=[System.Text.StringBuilder]::new(1800)
    [void][NativeWFInstallerTest]::GetWindowText($h,$buf,$buf.Capacity)
    $txt=$buf.ToString()
    if($txt.Length -gt 800){$txt=$txt.Substring(0,800)}
    $children+=@{id=[NativeWFInstallerTest]::GetDlgCtrlID($h);text=$txt}
  }
  $output=@{case=$label;kind='real_installer_failure_dialog';children=$children}
  $safeName=$label -replace '[^a-zA-Z0-9_\-]','_'
  $output | ConvertTo-Json -Depth 7 | Set-Content (Join-Path $out "pub010_modal_$safeName.json") -Encoding utf8
  Write-Host "INSTALL_FAILURE_DIALOG_CAPTURED $label child_count=$($children.Count)"
  return $children
}
function Run-NativeInstaller([string]$path,[string]$label,[int]$expectedExit){
  if(!(Test-Path -LiteralPath $path -PathType Leaf)){throw "Actual Windows installer missing for $label"}
  $perCase=Join-Path $out ("pub010_uia_"+$label+".json")
  if(Test-Path $regPath){$env:PUB010_TEST_OFFICE_SHIM='1'}else{Remove-Item Env:PUB010_TEST_OFFICE_SHIM -ErrorAction SilentlyContinue}
  # Reuse verified mature UIA strategy for modal. Main launch still sends
  # actual Win32 ID_INSTALL to the PID-verified OWN process.
  & python ci/pub032v21129/native_installer_uia.py --exe $path --case $label --report $perCase --timeout 100
  $driverExit=$LASTEXITCODE
  if(!(Test-Path -LiteralPath $perCase)){throw "UIA driver produced no evidence: $label exit=$driverExit"}
  $e=Get-Content -LiteralPath $perCase -Raw -Encoding UTF8 | ConvertFrom-Json
  $results.Add(@{case=$label;real_windows_process=$e.real_win32_exe;
    native_gui_started=$e.main_window_seen;real_install_command=$e.install_button_sent;
    process_exit=$e.exit_code;expected_exit=$expectedExit;actual_failure_modal=$e.failure_modal_seen;
    actual_failure_code=$e.WF_error;pywinauto_confirmed=$e.modal_uia_ok;
    actual_excel_macros_executed=$false;office_shim_only=$e.office_test_shim_only})
  Write-Host "PUB010_NATIVE_CASE=$label actual_exit=$($e.exit_code) expected=$expectedExit actual_WF=$($e.WF_error) UIA=$($e.modal_uia_ok)"
  if($driverExit -ne 0){throw "UIA installer driver failure: $label; exit=$driverExit"}
  if($e.exit_code -ne $expectedExit){throw "Actual native installer returned unexpected code $($e.exit_code) for $label (expected $expectedExit)"}
  if(!$e.main_window_seen -or !$e.install_button_sent){throw "No real native GUI command was exercised: $label"}
  if($expectedExit -ne 0){
    if(!$e.failure_modal_seen -or !$e.modal_uia_ok -or $e.WF_error -ne $expectedExit){
      throw "Installer negative test did not prove expected modal WF-${expectedExit}: $label"
    }
  }else{
    if($e.failure_modal_seen){throw "Supposed successful installer showed failure dialog: $label"}
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
  # The App Paths default value is exactly what resolve_excel() reads.
  Set-Item -Path $regPath -Value (Join-Path $excelStub 'EXCEL.EXE')
  $readback=(Get-Item -Path $regPath).GetValue('')
  if($readback -ne (Join-Path $excelStub 'EXCEL.EXE')){throw 'Office test shim App Paths registry readback failed'}
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
