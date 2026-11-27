# boot_skip_test.ps1 [-Screens HealthWarning,...] [-Button 0x0008] [-Videos 0|1] [-Settle 1.0]
# START (or another pad mask) on each boot screen: one launch per screen, the pad press is sent
# $Settle seconds after "Switching Screen ... to <screen>" appears in the game's own log (PORT_GAME_LOG),
# then the script waits for the next screens and prints what the game switched to and the window title
# (FPS unchanged for 10 s = frozen: the game is then LEFT RUNNING for inspection, freeze rule).
# The patch under test: port/psarc_edits.json, entry /ui/fe/boot_sequence.xml (docs\hle.md "Skipping the
# boot screens"). -Videos 1 plays the real movies (PORT_PLAY_VIDEOS=1, FFmpeg needed).
param(
    [string[]]$Screens = @('HealthWarning', 'LegalInformation', 'AutoSaveWarning', 'SCEEPresents', 'EvolutionStudios', 'GameIntro'),
    [string]$Button = '0x0008 4',
    [int]$Videos = 0,
    [double]$Settle = 1.0,
    [int]$Timeout = 150
)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
$log = Join-Path $port 'run.log'
$pad = Join-Path $env:TEMP 'motorstorm_pad.txt'
function Send-Pad([string]$m) {
    for ($t = 0; ; $t++) { try { Set-Content -Path $pad -Value $m -NoNewline -ErrorAction Stop; break } catch { if ($t -ge 50) { throw }; Start-Sleep -Milliseconds 20 } }
}
foreach ($scr in $Screens) {
    Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
    Start-Sleep 3
    Send-Pad ''
    if (Test-Path $log) { Move-Item $log (Join-Path $port 'run.prev.log') -Force }
    $env:PAD_FILE = $pad; $env:PORT_GAME_LOG = '1'; $env:PORT_PLAY_VIDEOS = "$Videos"
    Start-Process -FilePath cmd.exe -ArgumentList '/c', (Join-Path $port 'run.bat') -WindowStyle Minimized
    Remove-Item Env:PAD_FILE, Env:PORT_GAME_LOG, Env:PORT_PLAY_VIDEOS
    $t0 = Get-Date; $sent = $false; $result = 'screen not reached'
    while (((Get-Date) - $t0).TotalSeconds -lt $Timeout) {
        Start-Sleep -Milliseconds 300
        if (-not (Test-Path $log)) { continue }
        $txt = Get-Content $log -Raw -ErrorAction SilentlyContinue
        if (-not $sent -and $txt -match ('Switching Screen "[^"]*" to "' + $scr + '"')) {
            Start-Sleep -Milliseconds ([int]($Settle * 1000))
            Send-Pad $Button; Start-Sleep -Milliseconds 400; Send-Pad ''
            $sent = $true; $tSent = Get-Date
        }
        if ($sent -and ((Get-Date) - $tSent).TotalSeconds -gt 8) { break }
    }
    $seq = (Select-String -Path $log -Pattern 'Switching Screen "[^"]*" to "([^"]*)"' | ForEach-Object { $_.Matches[0].Groups[1].Value }) -join ' > '
    $gp = Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    $title = if ($gp) { $gp.Refresh(); $gp.MainWindowTitle } else { 'NO PROCESS' }
    $ok = $sent -and ($seq -match ($scr + '.*> TitleScreen'))
    Write-Host ("[{0}] START sent: {1}; reached TitleScreen right after: {2}`n   {3}`n   {4}" -f $scr, $sent, $ok, $seq, $title)
}
Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Confirm:$false
