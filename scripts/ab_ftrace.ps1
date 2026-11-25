# Precise A/B of two (or more) exes: 16 s of frame timeline (PS3_FTRACE) on the start line of the
# bridge race, 30 FPS cap lifted, runs alternated. Use it when the expected difference is under
# ~2 FPS: the title FPS of race_perf.ps1 moves +-1.5 FPS from one run to the next with the same exe
# (2026-11-24: 28.6 then 31.0), the frame median of a 16 s trace +-0.5 ms.
#   scripts\ab_ftrace.ps1 -Exes @{ base = ''; new = 'E:\ms_perf\lr\build\MotorStormApocalypse.exe' } `
#       -Order base,new,new,base -Tag lr
# An empty path = the exe of port\build. ~4.5 min a run; leave the machine alone meanwhile.
# Output: E:\ms_perf\abft\<tag>_<n>_<arm>.txt (traces) and E:\ms_perf\abft\<tag>.txt (per run:
# frames, frame median / mean, main thread running and its wait sites, from ftrace_idle.py).
param(
    [hashtable]$Exes = @{ base = '' },
    [string[]]$Order = @('base'),
    [string]$Tag = 'ab',
    [string]$Track = 'pont',
    [hashtable]$Env = @{},
    [hashtable]$ArmEnv = @{}
)
$rp = Join-Path $PSScriptRoot 'race_perf.ps1'
$fi = Join-Path $PSScriptRoot 'ftrace_idle.py'
$dir = 'E:\ms_perf\abft'; New-Item -ItemType Directory -Force $dir | Out-Null
$out = Join-Path $dir "$Tag.txt"
Add-Content $out ("started " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + " order: " + ($Order -join ' '))
$n = 0
foreach ($arm in $Order) {
    $n++
    if (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue) { Add-Content $out 'GAME ALREADY RUNNING: stopped'; break }
    $tr = ("$dir\${Tag}_${n}_$arm.txt") -replace '\\', '/'
    # The start line is reached 195 s after the launch on a quiet machine, 199-203 s under
    # background load: with 62 s of idle the window 232..248 s is inside the idle phase either way.
    # (240..256 lost a trace on 2026-11-24: the quiet run ended at 258 s, before the file was written.)
    $e = @{ GCM_SEMA_ACQUIRE = '0'; PS3_FTRACE = "232:16:$tr" } + $Env
    if ($Exes[$arm]) { $e['PORT_EXE'] = $Exes[$arm] }
    if ($ArmEnv[$arm]) { foreach ($k in $ArmEnv[$arm].Keys) { $e[$k] = $ArmEnv[$arm][$k] } }
    try {
        & $rp -Label "abft $Tag $arm" -Track $Track -IdleSeconds 62 -DriveSeconds 2 -Env $e *> $null
        $r = & python $fi $tr 2>&1 | Select-Object -First 12 | Where-Object { $_ -match '^frames:|^  running|^  usleep|^  syscall' }
        Add-Content $out ("== $n $arm " + (Get-Date -Format 'HH:mm:ss'))
        Add-Content $out ($r -join "`n")
    } catch { Add-Content $out ("== $n $arm FAILED: " + $_.Exception.Message) }
    Start-Sleep 6
}
Add-Content $out ("finished " + (Get-Date -Format 'HH:mm:ss'))
Get-Content $out -Tail (6 * $Order.Count + 2)
