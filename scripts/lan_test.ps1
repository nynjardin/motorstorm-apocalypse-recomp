# Several instances of the port on this machine, in the title's LAN mode (port\run_lan.bat):
# instance 1 hosts a private game, the others open "Trouver une partie" (the list of LAN games).
#   scripts\lan_test.ps1 [-Out E:\ms_perf\net\lan1] [-Players 2] [-Join] [-Start] [-Drive]
#                        [-Races 1] [-LeaveAt <s>] [-KeepRunning] [-GameLog '1']
# -Players n: n instances (default 2): instance k is 127.0.0.k, "Pilote<k>", window "ps3recomp P<k>".
# -Join: every other instance then presses X on the first game of the list.
# -Start (with -Join): the host presses UP + X (DEPART), then nothing is pressed for -StartWait
#   seconds: all the windows captured at the same instant every 10 s (s<t>_h.png = host, s<t>_j.png =
#   instance 2, s<t>_p<k>.png = instance k), then the stages each went through. Environment set
#   before the call reaches every game (e.g. PORT_SIM_RT).
# -Drive (with -Start): all then drive straight ahead (R2) for -DriveSeconds, instance k starting
#   (k-1) x -DriveLag seconds after the host; captures every 3 s meanwhile.
# -Races n (with -Start): once everybody is back in the lobby the host presses X (DEPART) again,
#   n races in all; -StartWait is the time watched after EACH departure (captures r<n>s<t>_*.png
#   from the second race on).
# -LeaveAt s (with -Start): the last instance is killed s seconds after the first race started
#   (a player whose machine dies in the middle of a race).
# Screenshots (h_*.png = host, j_*.png / p<k>_*.png = the others) and the logs go to -Out; the
# summary printed at the end is what they exchanged (sys_net lines grouped) and the title's own
# messages about finding / joining ([game] lines, PORT_GAME_LOG). The games are stopped at the end
# unless -KeepRunning. Scripted pads: %TEMP%\motorstorm_pad.txt (host), motorstorm_pad<k>.txt.
# See the captures of a whole run at once: scripts\pair_sheet.py <Out>. docs\reseau.md.
param(
    [string]$Out = 'E:\ms_perf\net\lan_test',
    [int]$Players = 2,
    [switch]$Join,
    [switch]$KeepRunning,
    [string]$GameLog = '1',
    [int]$JoinWait = 25,
    [switch]$Start,            # with -Join: the host then presses UP + X (DEPART) and nothing else
    [int]$StartWait = 150,     # seconds watched after DEPART (captures every 10 s)
    [switch]$Drive,            # with -Start: R2 held on all once the race runs (see the loop)
    [int]$DriveSeconds = 60,
    [int]$DriveLag = 3,
    [int]$Races = 1,
    [int]$LeaveAt = 0,
    [switch]$V106              # the 1.06 build (PORT_V106): log run106.log, After Party page instead of the title
)
$ErrorActionPreference = 'Stop'
$port = Join-Path $PSScriptRoot '..\port'
New-Item -ItemType Directory -Force $Out | Out-Null
# A game stopped a moment ago (the end of a previous run of this script) may still be closing.
for ($w = 0; $w -lt 15 -and (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue); $w++) { Start-Sleep 1 }
if (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue) { throw 'a game is already running' }
if ($Players -lt 2 -or $Players -gt 8) { throw '-Players: 2 to 8' }
# Per instance: pad file, log, window title pattern, tag of its captures.
$inst = @(1..$Players | ForEach-Object {
    [pscustomobject]@{
        N     = $_
        Pad   = Join-Path $env:TEMP $(if ($_ -eq 1) { 'motorstorm_pad.txt' } else { "motorstorm_pad$_.txt" })
        Log   = Join-Path $port $(if ($_ -eq 1) { $(if ($V106) { 'run106.log' } else { 'run.log' }) } else { "run_p$_.log" })
        Title = $(if ($_ -eq 1) { '^ps3recomp \|' } else { "^ps3recomp P$_ \|" })
        Tag   = $(if ($_ -eq 1) { 'h' } elseif ($_ -eq 2) { 'j' } else { "p$_" })
        Name  = $(if ($_ -eq 1) { 'HOST' } else { "INSTANCE $_" })
    } })
$hostI = $inst[0]; $others = @($inst | Select-Object -Skip 1)
function Send-Pad($to, [string]$m, [int]$w) {       # the same press on one or several instances
    foreach ($i in @($to)) {
        for ($t = 0; ; $t++) { try { Set-Content -Path $i.Pad -Value $m -NoNewline -ErrorAction Stop; break } catch { if ($t -ge 50) { throw }; Start-Sleep -Milliseconds 20 } }
    }
    if ($w -gt 0) { Start-Sleep $w }
}
function Shot([string]$n, $i) { (& (Join-Path $PSScriptRoot 'screenshot.ps1') -Out (Join-Path $Out "$($i.Tag)_$n.png") -Title $i.Title | Select-Object -Last 1) -replace '^saved ', '' }
function Count-Log($i, [string]$pattern) { @(Select-String -Path $i.Log -Pattern $pattern).Count }
function Wait-Title($i) {
    $t0 = Get-Date
    # START skips each boot screen (port\psarc_edits.json); the title screen has its own log line
    # (PORT_GAME_LOG must let "Switching Screen" through: '1' does).
    $boot = 'HealthWarning', 'LegalInformation', 'AutoSaveWarning', 'SCEEPresents', 'EvolutionStudios', 'VidIntermediaryScreen', 'GameIntro'
    $lastStart = [datetime]::MinValue
    $titlePat = $(if ($V106) { 'LogicFullyActive \[AnnouncementDisplayLogic\]' } else { 'to "TitleScreen"' })
    while (-not (Test-Path $i.Log) -or -not (Select-String -Path $i.Log -Pattern $titlePat -Quiet)) {
        if (((Get-Date) - $t0).TotalSeconds -gt 300) { throw "$($i.Name): title screen not reached" }
        Start-Sleep -Milliseconds 500
        if (Test-Path $i.Log) {
            $cur = Select-String -Path $i.Log -Pattern 'Switching Screen "[^"]*" to "([^"]*)"' | Select-Object -Last 1
            if ($cur -and ($boot -contains $cur.Matches[0].Groups[1].Value) -and ((Get-Date) - $lastStart).TotalSeconds -gt 1.5) {
                try { Set-Content -Path $i.Pad -Value '0x0008 4' -NoNewline -ErrorAction Stop; Start-Sleep -Milliseconds 300; Set-Content -Path $i.Pad -Value '' -NoNewline -ErrorAction Stop } catch { }
                $lastStart = Get-Date
            }
        }
    }
    if ($V106) { Start-Sleep 6 } else { Start-Sleep 2 }
    Write-Host ("{0}: title after {1:N0}s" -f $i.Name, ((Get-Date) - $t0).TotalSeconds)
}
function To-Multiplayer($to) {
    Send-Pad $to '0x4000 8' 30      # X: title -> main menu (slow to appear)
    Send-Pad $to '0x0040 4' 4       # DOWN: "Pour le fun"
    Send-Pad $to '0x4000 8' 8       # X
    Send-Pad $to '0x0040 4' 4       # DOWN: "Multijoueur"
    Send-Pad $to '0x4000 8' 12      # X -> the Multiplayer home
}
foreach ($i in $inst) { Set-Content -Path $i.Pad -Value '' -NoNewline; if (Test-Path $i.Log) { Remove-Item $i.Log -Force } }
$env:PORT_GAME_LOG = $GameLog; $env:PORT_GAME_LOG_MAX = '40'; $env:PS3_NET_TRACE = '1'
if ($V106) { $env:PORT_V106 = '1' }
$env:PORT_LAN_LOCAL = "$Players"   # instance k = 127.0.0.k, broadcasts sent to all the others (run_lan.bat)
$env:PAD_FILE = $hostI.Pad         # instance 1 only: run_lan.bat sets the pad file of the others
Start-Process -FilePath cmd.exe -ArgumentList '/c', (Join-Path $port 'run_lan.bat'), 'Pilote1', '1' -WindowStyle Minimized
Start-Sleep 3
Remove-Item env:PAD_FILE
foreach ($i in $others) {
    Start-Process -FilePath cmd.exe -ArgumentList '/c', (Join-Path $port 'run_lan.bat'), "Pilote$($i.N)", "$($i.N)" -WindowStyle Minimized
    Start-Sleep 2
}
Remove-Item env:PORT_GAME_LOG, env:PORT_GAME_LOG_MAX, env:PS3_NET_TRACE, env:PORT_LAN_LOCAL, env:PORT_V106 -ErrorAction SilentlyContinue
foreach ($i in $inst) { Wait-Title $i }
Start-Sleep 20
To-Multiplayer $hostI
Shot 'home' $hostI
Send-Pad $hostI '0x0040 4' 2          # DOWN: "Partie privee" (the focus opens on "Trouver une partie")
Send-Pad $hostI '0x4000 8' 4          # X: "Partie privee"
Send-Pad $hostI '0x4000 8' 12         # X: the game mode -> the lobby
Shot 'lobby' $hostI
To-Multiplayer $others                # all the others at once
foreach ($i in $others) { Shot 'home' $i }
Send-Pad $others '0x4000 8' 10        # X: "Trouver une partie" = the list of the LAN games (port\psarc_edits.json)
foreach ($i in $others) { Shot 'browser' $i }
if ($Join) {
    # One after the other: each arrival is a full exchange with everybody already there.
    foreach ($i in $others) { Send-Pad $i '0x4000 8' $(if ($Players -gt 2) { 12 } else { 0 }) }
    Start-Sleep $JoinWait
    foreach ($i in $inst) { Shot 'joined' $i }
}
if ($Join -and $Start) {
    for ($race = 1; $race -le $Races; $race++) {
        $pre = if ($race -gt 1) { "r$race" } else { '' }
        $racing0 = Count-Log $hostI 'now RACING'
        if ($race -eq 1) { Send-Pad $hostI '0x0010 4' 2 }   # UP: "DEPART" (after a join the focus is on the entry below)
        Send-Pad $hostI '0x4000 8' 1                        # X (back from a race the focus is on DEPART)
        $tStart = Get-Date; $tRace = $null; $t = 10; $driven = @{}; $left = $false
        while ($t -le $StartWait) {
            if (-not $tRace -and (Count-Log $hostI 'now RACING') -gt $racing0) {
                $tRace = Get-Date
                Write-Host ("race $race`: racing {0:N0}s after DEPART" -f ($tRace - $tStart).TotalSeconds)
            }
            if ($tRace) {
                $sinceRace = ((Get-Date) - $tRace).TotalSeconds
                if ($Drive) {
                    foreach ($i in $inst) {
                        $lag = ($i.N - 1) * $DriveLag
                        if (-not $driven[$i.N] -and $sinceRace -ge $lag -and (Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -match $i.Title })) {
                            $driven[$i.N] = $true; Send-Pad $i ("0x0200 {0}ms" -f (($DriveSeconds - $lag) * 1000)) 0
                        }
                    }
                }
                if ($LeaveAt -gt 0 -and $race -eq 1 -and -not $left -and $sinceRace -ge $LeaveAt) {
                    $left = $true; $last = $inst[-1]
                    Get-Process MotorStormApocalypse | Where-Object { $_.MainWindowTitle -match $last.Title } | Stop-Process -Force
                    Write-Host ("{0} killed {1:N0}s after the race started" -f $last.Name, $sinceRace)
                }
            }
            $el = ((Get-Date) - $tStart).TotalSeconds
            if ($el -lt $t) { Start-Sleep -Milliseconds ([int]([math]::Min(1.0, $t - $el) * 1000)); continue }
            & (Join-Path $PSScriptRoot 'screenshot_pair.ps1') -Prefix (Join-Path $Out ("{0}s{1:D3}" -f $pre, $t)) | ForEach-Object { Write-Host $_ }
            $t += if ($Drive -and $tRace -and ((Get-Date) - $tRace).TotalSeconds -lt $DriveSeconds) { 3 } else { 10 }
            # the next race: as soon as the host is back in the lobby after this one
            if ($race -lt $Races -and $tRace -and (Select-String -Path $hostI.Log -Pattern 'Switching Screen "\w+" to "RaceLobby"' | Select-Object -Last 1 | Where-Object { $_.LineNumber -gt (Select-String -Path $hostI.Log -Pattern 'now RACING' | Select-Object -Last 1).LineNumber })) {
                Write-Host ("race $race`: back in the lobby {0:N0}s after DEPART" -f ((Get-Date) - $tStart).TotalSeconds)
                Start-Sleep 8; break
            }
        }
    }
    foreach ($i in $inst) {
        Write-Host "=== $($i.Name) after DEPART"
        Get-Content $i.Log | Select-String '^\[(game|port-net)\].*(Switching Screen|SetLogicActive\(\[1|LogicFullyActive|OTG action|Creating OTG|completed on error|otgError|COUNTDOWN|TearDown|Shutdown|Loading|Disconnect|FAIL|render state|RESULTS|DISQUALIF|Players met|Host|Master|left|Left|Leav|Remov|Migrat)' | Where-Object { $_.Line -notmatch 'EvoCommunityActionNews' } |
            Select-Object -Last 60 | ForEach-Object { $_.Line.Substring(0, [math]::Min(170, $_.Line.Length)) }
    }
}
Write-Host '=== trouble lines (a loading that never ends, the PUTLLC race of toolkit patch #65, chips banked)'
foreach ($i in $inst) {
    $bad = @(Select-String -Path $i.Log -Pattern 'HOTREAD|TOO LONG LOADING|PUTLLC: a store|chips banked|EventFlagWait BLOCKED|FROZEN')
    Write-Host ("{0}: {1}" -f $i.Name, $(if ($bad) { ($bad | Group-Object { $k = $_.Line -replace '0x[0-9A-Fa-f]+|-?\d+', 'N'; $k.Substring(0, [math]::Min(60, $k.Length)) } | ForEach-Object { "{0} x {1}" -f $_.Count, $_.Group[0].Line.Substring(0, [math]::Min(110, $_.Group[0].Line.Length)) }) -join ' | ' } else { 'none' }))
}
foreach ($i in $inst) {
    Copy-Item $i.Log (Join-Path $Out $(if ($i.N -eq 1) { 'run_host.log' } else { "run_p$($i.N).log" })) -Force
    Write-Host "=== $($i.Name) sockets"
    Get-Content $i.Log | Select-String '^\[sys_net' | Group-Object { ($_.Line -replace '\d\d:\d\d:\d\d\.\d+', 'T') } | Sort-Object Count -Descending |
        Select-Object -First 14 | ForEach-Object { "{0,5}  {1}" -f $_.Count, $_.Name }
    Write-Host "=== $($i.Name) game messages"
    Get-Content $i.Log | Select-String '^\[game\].*(Game Found|GameName|Game Info:|Address =|clients\[|RefreshGameList|NetLANFind|WorldConnect -|WorldJoin|NetJoin|Connecting to host|LocalJoin|RemoteClient|Client IP|Remote Player|FAIL|OnlineError|TCustomGames|RaceLobby"|ConnectionStatus|IGNORED|Host Max)' |
        Select-Object -First 40 | ForEach-Object { $_.Line.Substring(0, [math]::Min(170, $_.Line.Length)) }
}
if (-not $KeepRunning) { Get-Process MotorStormApocalypse -ErrorAction SilentlyContinue | Stop-Process -Force }
