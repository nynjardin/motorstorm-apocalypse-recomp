@echo off
rem MotorStorm: Apocalypse above 30 FPS at normal game speed: the title's real-time simulation
rem clock (PORT_SIM_RT=1, see run.bat and docs\hle.md "Above 30 FPS at normal speed").
rem Double-click this file instead of run.bat. The window title shows the FPS.
set "PORT_SIM_RT=1"
call "%~dp0run.bat" %*
