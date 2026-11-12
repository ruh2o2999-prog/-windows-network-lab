# V8.12/PUB-027 L3: reproduce the underlying Win32 locked-file rename behavior.
# Isolated fabricated files ONLY; this is not the full publisher/installer acceptance.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$out=Join-Path (Get-Location) 'out'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$reportPath=Join-Path $out 'pub027_v812_native_lock_minimal.json'
$root=Join-Path $env:RUNNER_TEMP ('pub027_v812_synth_'+$env:GITHUB_RUN_ID)
$live=Join-Path $root 'live';$bak=Join-Path $root 'bak'
$result=[ordered]@{
  issue_id='PUB-027'
  policy='V8.12'
  scope='Real Win32 MoveFileExW lock-failure/partial-restore; synthetic minimal files, NOT product installation'
  host='windows-2022'
  source_version='V2.11.2.9 RC1 function behavior hypothesis'
  expected_failure='file lock denies MOVEFILE_WRITE_THROUGH'
  observed_win32_error=$null
  backup_first_move_ok=$false
  locked_move_rejected=$false
  unchanged_locked_file=$false
  rollback_first_move_ok=$false
  rollback_original_bytes_verified=$false
  post_unlock_move_ok=$false
  passed=$false
}
$lockedHandle=$null
try {
  if(Test-Path $root){throw 'Test root exists; refusing to reuse'}
  New-Item -ItemType Directory -Force -Path $live,$bak | Out-Null
  $first=Join-Path $live 'a_original.txt';$firstBackup=Join-Path $bak 'a_original.txt'
  $lockfile=Join-Path $live 'z_locked_workbook.xlsm';$lockBackup=Join-Path $bak 'z_locked_workbook.xlsm'
  [IO.File]::WriteAllBytes($first,[Text.Encoding]::UTF8.GetBytes('SYNTHETIC-OLD-FIRST'))
  [IO.File]::WriteAllBytes($lockfile,[Text.Encoding]::UTF8.GetBytes('SYNTHETIC-OLD-WORKBOOK'))
  $shaFirst=(Get-FileHash $first -Algorithm SHA256).Hash
  $shaWorkbook=(Get-FileHash $lockfile -Algorithm SHA256).Hash
  Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Pub027V812Win32 {
  [DllImport("kernel32.dll", EntryPoint="MoveFileExW", CharSet=CharSet.Unicode, SetLastError=true)]
  [return:MarshalAs(UnmanagedType.Bool)]
  public static extern bool MoveFileEx(string src, string dst, uint flags);
}
'@
  $move=[uint32]0x8 # MOVEFILE_WRITE_THROUGH, same flag as product backup function
  $lockedHandle=[IO.File]::Open($lockfile,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)
  if(![Pub027V812Win32]::MoveFileEx($first,$firstBackup,$move)){throw 'First independent file failed to back up'}
  $result.backup_first_move_ok=$true
  $t=[Diagnostics.Stopwatch]::StartNew()
  $moved=[Pub027V812Win32]::MoveFileEx($lockfile,$lockBackup,$move)
  $e=[Runtime.InteropServices.Marshal]::GetLastWin32Error()
  $t.Stop()
  $result.observed_win32_error=$e
  $result.lock_attempt_milliseconds=$t.ElapsedMilliseconds
  if($moved){throw 'Exclusively locked workbook unexpectedly moved'}
  if($e -notin @(32,5)){throw "Unexpected locked-file error code: $e"}
  if($t.Elapsed.TotalSeconds -gt 5){throw 'Win32 lock failure did not return promptly'}
  $result.locked_move_rejected=$true
  # FileShare.None correctly prevents Get-FileHash from opening the locked file.
  # Check existence while locked; SHA256 only after releasing our own handle.
  if(!(Test-Path -LiteralPath $lockfile) -or (Test-Path -LiteralPath $lockBackup)){
     throw 'Locked original was moved or vanished during denied rename'
  }
  if(![Pub027V812Win32]::MoveFileEx($firstBackup,$first,$move)){throw 'Previously backed up file failed rollback'}
  $result.rollback_first_move_ok=$true
  if(!(Test-Path $first) -or (Get-FileHash $first -Algorithm SHA256).Hash -ne $shaFirst){
     throw 'Previously moved original is not byte-identical after rollback'
  }
  $lockedHandle.Dispose();$lockedHandle=$null
  if((Get-FileHash $lockfile -Algorithm SHA256).Hash -ne $shaWorkbook){
     throw 'Locked original changed after lock release'
  }
  $result.unchanged_locked_file=$true
  $result.rollback_original_bytes_verified=$true
  if(![Pub027V812Win32]::MoveFileEx($lockfile,$lockBackup,$move)){throw 'Unlocked workbook failed normal rename'}
  if((Get-FileHash $lockBackup -Algorithm SHA256).Hash -ne $shaWorkbook){throw 'Unlocked file identity changed'}
  $result.post_unlock_move_ok=$true
  $result.passed=$true
  Write-Host "PUB027_V812_MINIMAL_WIN32_LOCK_PASS error=$e duration_ms=$($t.ElapsedMilliseconds)"
} catch {
  $result.error=$_.Exception.Message
  throw
} finally {
  if($lockedHandle){$lockedHandle.Dispose()}
  $result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $reportPath -Encoding UTF8
  if(Test-Path $root){Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue}
}
