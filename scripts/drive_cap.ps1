# RSX frame captures WHILE DRIVING the reference race (scripted R2): launches race_perf.ps1 with
# RSX_CAP_GATE and asks for <Caps> captures, the first <After> seconds into the drive phase, 4 s apart.
# For defects that only show in motion (a buffer one frame late: compare two surfaces of ONE capture).
#   scripts\drive_cap.ps1 -Label base
#   scripts\drive_cap.ps1 -Label old -Env @{DS_CONV_BOUND='0'}
#   scripts\drive_cap.ps1 -Label pack -Idle 0 -After 5 [-Track quai]   # leaving with the pack: other vehicles close
# Results: E:\ms_perf\drivecap_<label>\frame_50, frame_51, ... (manifest.txt, fps.hlsl, rt_*.bmp, ds_*.bmp)
param(
    [string]$Label = 'base',
    [hashtable]$Env = @{},
    [int]$Caps = 3,
    [int]$After = 12,
    [int]$Idle = 8,              # seconds on the start line first (0 = leave with the pack)
    [string]$Track = 'pont'
)
$dir = "E:\ms_perf\drivecap_$Label"
New-Item -ItemType Directory -Force $dir | Out-Null
$gate = Join-Path $env:TEMP 'ms_capgate.txt'
Remove-Item $gate -ErrorAction SilentlyContinue
$e = @{} + $Env
$e['RSX_CAP_GATE'] = $gate; $e['RSX_CAP_DIR'] = $dir
$marks = Join-Path $PSScriptRoot '..\port\race_perf_marks.txt'
$job = Start-Job -ArgumentList $marks, $gate, $Caps, $After -ScriptBlock {
    param($marks, $gate, $caps, $after)
    Start-Sleep 60   # the marks file is reset when race_perf starts
    for ($i = 0; $i -lt 600; $i++) {
        if ((Test-Path $marks) -and (Select-String -Path $marks -Pattern 'drive begin' -Quiet)) { break }
        Start-Sleep 1
    }
    Start-Sleep $after
    for ($c = 0; $c -lt $caps; $c++) { Set-Content -Path $gate -Value '1' -NoNewline; Start-Sleep 4 }
}
& (Join-Path $PSScriptRoot 'race_perf.ps1') -Label "drivecap $Label [controle, FPS faux]" -Env $e -Track $Track -IdleSeconds $Idle -DriveSeconds ($After + $Caps * 4 + 6) 2>&1 | Select-Object -Last 3
Receive-Job $job -Wait -ErrorAction SilentlyContinue | Out-Null
Write-Host "[drive_cap] $Label -> $dir"
Get-ChildItem $dir -Directory | ForEach-Object { "{0}: {1} files" -f $_.Name, (Get-ChildItem $_.FullName).Count } | Write-Host
