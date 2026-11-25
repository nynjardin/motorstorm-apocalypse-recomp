@echo off
rem MotorStorm: Apocalypse on the local network, no server: the title's own LAN mode (SCE-RT
rem peer-to-peer host + LAN find by UDP broadcast on port 3658). docs\reseau.md.
rem   port\run_lan.bat [name] [instance]
rem     name      the player's name, 3-16 letters / digits / - / _ (default: Pilote<instance>)
rem     instance  1 (default), or 2, 3... = another copy of the game on THIS machine, for tests:
rem               its own save, HDD cache, log (run_p<N>.log) and pad file.
rem In the game: "Pour le fun" > "Multijoueur", then "Partie privee" to host, "Trouver une partie" to
rem look for the games of the network.
rem Environment, set before calling:
rem   PS3_NET_IP=<a.b.c.d>   the network card to play on (default: the one of the default route).
rem                          A virtual LAN (ZeroTier, Radmin VPN...) = play over the Internet.
rem   PS3_NET_PEERS=<ip,ip>  also send the LAN broadcasts to these addresses (no broadcast there).
rem   PORT_LAN_LOCAL=<n>     test on one machine with n instances (1 = 2): instance N is
rem                          127.0.0.N (scripts\lan_test.ps1 [-Players n]).
setlocal
set "INST=%~2"
if "%INST%"=="" set "INST=1"
set "NAME=%~1"
if "%NAME%"=="" set "NAME=Pilote%INST%"

rem The title's LAN back end instead of the Medius one (port\net_hooks.cpp).
set "PORT_NET_LAN=1"
rem Real host sockets; the NP manager says "signed in" (PSNR_SERVER is only what makes it say so:
rem nothing is contacted there, this title does not use sceNpMatching2).
set "PS3_NET_ONLINE=1"
set "PSNR_SERVER=127.0.0.1"
set "PORT_NETCTL_TOOLKIT=1"
set "PS3_NP_ONLINE_ID=%NAME%"
rem The title's community server is gone: never look its name up (each lookup froze the game).
set "PS3_HTTP_BLOCK=online.scee.com"
rem The title's P2P datagram socket must not want UDP 3658: its own LAN find already holds that
rem port (the toolkit maps a P2P socket to one real UDP port, PS3_NET_P2P_PORT, default 3658, and
rem the title then retried the bind for ever). Same value on every PC of the network.
set "PS3_NET_P2P_PORT=3659"

rem The title's real-time game clock (docs\hle.md "Above 30 FPS at normal speed"), 30 FPS at most:
rem as shipped the game time advances by 1/30 s per FRAME, so a machine under 30 FPS lives a slower
rem race than the others and the timers of the players drift apart (measured with two instances at
rem 22 FPS: the elimination countdown lost 7.3 s in 10 s, 0.13 s more on one than on the other;
rem with this clock: 9.97 and 9.99 s). Set PORT_SIM_RT=0 before calling to get the shipped clock.
if not defined PORT_SIM_RT set "PORT_SIM_RT=1"
if not defined PORT_SIM_INTERVAL set "PORT_SIM_INTERVAL=2"

rem One machine, several instances: each is its own loopback address, and "broadcasts" are sent
rem to the other one: toolkit local patch #62.
rem PORT_LAN_LOCAL = how many instances (1 = 2): the peers are all the others, 127.0.0.1..N.
if not defined PORT_LAN_LOCAL goto nolocal
set "PS3_NET_IP=127.0.0.%INST%"
set "LOCALN=%PORT_LAN_LOCAL%"
if %LOCALN% LSS 2 set "LOCALN=2"
set "PS3_NET_PEERS="
setlocal enabledelayedexpansion
set "P="
for /L %%k in (1,1,%LOCALN%) do if not "%%k"=="%INST%" set "P=!P!,127.0.0.%%k"
endlocal & set "PS3_NET_PEERS=%P:~1%"
:nolocal
rem The card of the default route (lowest metric), not the first address of the host name: on a
rem machine with VPN adapters that one was a VPN.
if not defined PS3_NET_IP for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$r = Get-NetRoute -DestinationPrefix 0.0.0.0/0 -ErrorAction SilentlyContinue | Sort-Object { $_.RouteMetric + $_.InterfaceMetric } | Select-Object -First 1; if ($r) { (Get-NetIPAddress -InterfaceIndex $r.InterfaceIndex -AddressFamily IPv4 | Select-Object -First 1).IPAddress }"`) do set "PS3_NET_IP=%%i"
echo [run_lan] %NAME%, instance %INST%, address %PS3_NET_IP%

if "%INST%"=="1" goto run
rem ---- another instance on the same machine ------------------------------------------------
set "PORT_RUN_LOG=%~dp0run_p%INST%.log"
set "PAD_FILE=%TEMP%\motorstorm_pad%INST%.txt"
set "PS3_TITLE=ps3recomp P%INST%"
set "PS3_GAMEDATA_ROOT=%~dp0gamedata_p%INST%"
set "PS3_HDD0_ROOT=F:\Jeux\PS3\_recomp\BCES00484_p%INST%\dev_hdd0"
set "PS3_HDD1_ROOT=F:\Jeux\PS3\_recomp\BCES00484_p%INST%\dev_hdd1"
rem First use: start from copies of instance 1's save and HDD cache (1.2 GB on F:), so that this
rem instance does not replay the first-boot screens nor rebuild the cache.
if not exist "%PS3_GAMEDATA_ROOT%" robocopy "%~dp0gamedata" "%PS3_GAMEDATA_ROOT%" /E /NFL /NDL /NJH /NJS >nul
if not exist "%PS3_HDD1_ROOT%" robocopy "F:\Jeux\PS3\_recomp\BCES00484" "F:\Jeux\PS3\_recomp\BCES00484_p%INST%" /E /XD shader_cache /NFL /NDL /NJH /NJS >nul

:run
call "%~dp0run.bat"
