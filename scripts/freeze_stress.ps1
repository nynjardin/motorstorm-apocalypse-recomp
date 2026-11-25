# Freeze statistics under an artificial CPU load.
# Runs catch_freeze.ps1 one try at a time, -Tries times, with scripts\cpu_load.py burning -Load
# processes (the intermittent freeze of 2026-11-21 came mostly on a loaded machine). Each frozen
# try is recorded (log copied by catch_freeze, thread stacks / locks / SPU contexts dumped into
# <OutDir>\stress_<label>_<n>\), then the game is stopped and the next try starts. Prints
# "<label>: <frozen>/<tries> frozen" and appends it to <OutDir>\stress_results.txt.
#   scripts\freeze_stress.ps1 -Label fix -Tries 6 [-Load 10] [-Env @{SPU_SIG_OWED='0'}] [-KeepLast]
param(
    [string]$Label = 'run',
    [int]$Tries = 6,
    [int]$Load = 10,
    [hashtable]$Env = @{},
    [int]$MenuSeconds = 60,
    [string]$OutDir = 'E:\ms_perf\freeze',
    [switch]$KeepLast            # leave the last frozen game running for inspection
)
$py = 'I:\Projets\Recomp\.venv\Scripts\python.exe'
New-Item -ItemType Directory -Force $OutDir | Out-Null
# The workers are separate processes: they stop on the stop file (killing the parent leaves them running).
function Stop-Load { Set-Content -Path (Join-Path $env:TEMP 'cpu_load.stop') -Value 'stop'; Start-Sleep 2 }
$frozen = 0
for ($n = 1; $n -le $Tries; $n++) {
    if ($Load -gt 0) { Start-Process -FilePath $py -ArgumentList (Join-Path $PSScriptRoot 'cpu_load.py'), $Load, '900' -WindowStyle Hidden }
    $out = & (Join-Path $PSScriptRoot 'catch_freeze.ps1') -Tries 1 -MenuSeconds $MenuSeconds -OutDir $OutDir -Env $Env *>&1 | Out-String   # *>&1: catch_freeze reports with Write-Host
    Stop-Load
    if ($out -match 'FROZEN') {
        $frozen++
        $d = Join-Path $OutDir ("stress_{0}_{1}" -f $Label, $n)
        New-Item -ItemType Directory -Force $d | Out-Null
        & $py (Join-Path $PSScriptRoot 'host_stacks.py') --samples 10 --depth 14 2>&1 | Out-File "$d\stacks.txt" -Encoding utf8
        & $py (Join-Path $PSScriptRoot 'host_locks.py') 2>&1 | Out-File "$d\locks.txt" -Encoding utf8
        & $py (Join-Path $PSScriptRoot 'host_spuctx.py') 2>&1 | Out-File "$d\spuctx.txt" -Encoding utf8
        & $py (Join-Path $PSScriptRoot 'host_ppuctx.py') 2>&1 | Out-File "$d\main_ctx.txt" -Encoding utf8
        Copy-Item (Join-Path $PSScriptRoot '..\port\run.log') "$d\run.log" -ErrorAction SilentlyContinue
        Write-Output "try ${n}: FROZEN -> $d"
        if ($KeepLast -and $n -eq $Tries) { break }
    } else { Write-Output "try ${n}: ok" }
    Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
    Start-Sleep 4
}
$line = "{0} {1}: {2}/{3} frozen (load {4})" -f (Get-Date -Format 'yyyy-MM-dd HH:mm'), $Label, $frozen, $Tries, $Load
Add-Content -Path (Join-Path $OutDir 'stress_results.txt') -Value $line
Write-Output $line
