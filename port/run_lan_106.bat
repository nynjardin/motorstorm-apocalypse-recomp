@echo off
rem Multiplayer (LAN) with the 1.06 update build: PORT_V106=1 then run_lan.bat (same arguments: [name] [instance]).
rem run.bat alone has no multiplayer environment: the Multijoueur entry of the menu does nothing there.
set "PORT_V106=1"
call "%~dp0run_lan.bat" %*
