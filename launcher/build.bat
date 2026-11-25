@echo off
rem Build the launcher (Tauri 2: Rust in src-tauri\, the page in ui\, embedded in the exe).
rem Output: %CARGO_TARGET_DIR%\release\Launcher.exe. The target directory (~2 GB) is on E:, never
rem on I: (small disk). Then scripts\deploy_game.ps1 copies it into the game folder.
setlocal
if not defined CARGO_TARGET_DIR set "CARGO_TARGET_DIR=E:\ms_perf\launcher_target"
cd /d "%~dp0src-tauri"
"%USERPROFILE%\.cargo\bin\cargo.exe" build --release %*
echo exit code %ERRORLEVEL% (%CARGO_TARGET_DIR%\release\Launcher.exe)
