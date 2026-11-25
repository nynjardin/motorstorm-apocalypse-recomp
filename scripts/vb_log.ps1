# Frame pacing log of a running game: one line per -Chunk seconds with the window title and the
# vb_poll.py summary (vblanks/s, flips/s, histogram of vblanks per flip). Ends when the game exits
# (after having been seen) or after -MaxSeconds. See docs/hle.md "Frame pacing".
#   scripts\vb_log.ps1 -Out E:\ms_perf\vb_x.txt [-Chunk 15] [-MaxSeconds 600]
param([string]$Out = "", [int]$Chunk = 15, [int]$MaxSeconds = 600)
$py = 'I:/Projets/Recomp/.venv/Scripts/python.exe'
$poll = Join-Path $PSScriptRoot 'vb_poll.py'
$t0 = Get-Date; $seen = $false
while (((Get-Date) - $t0).TotalSeconds -lt $MaxSeconds) {
    $p = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $p) { if ($seen) { break }; Start-Sleep 2; continue }
    $seen = $true
    $r = (& $py $poll $Chunk 0.5 --quiet 2>&1 | Select-Object -Last 1)
    $p.Refresh()
    $line = "{0,4:N0}s {1} | {2}" -f ((Get-Date) - $t0).TotalSeconds, $p.MainWindowTitle, $r
    Write-Output $line
    if ($Out) { Add-Content -Path $Out -Value $line }
}
